from typing import TYPE_CHECKING, Optional

from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.signing import BadSignature
from django.core.signing import SignatureExpired
from django.core.signing import TimestampSigner
from django.db import models
from django.db.models import Q, QuerySet
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.urls import reverse
from wagtail.models import Orderable

from accounts.fields import DefaultOneToOneField

if TYPE_CHECKING:
    from home.models import Session, SessionMembership


class CustomUserQuerySet(QuerySet):
    def with_project_preference(
        self, project: "Project", session: "Session"
    ) -> "QuerySet[CustomUser]":
        """
        Filter users who have selected a specific project as a preference for a session.

        Args:
            project: The project to filter by
            session: The session context

        Returns:
            QuerySet of CustomUser objects who have this project preference
        """
        return self.filter(
            project_preferences__project=project,
            project_preferences__session=session,
        ).distinct()

    def with_invalid_project_preference(
        self, project: "Project", session: "Session"
    ) -> "QuerySet[CustomUser]":
        """
        Filter users whose project preferences conflict with the specified project.

        Returns users who have indicated project preferences for this session,
        but have NOT selected the specified project. These users would have
        an invalid/conflicting preference if assigned to a team working on
        the specified project.

        Users with no project preferences at all are NOT included in the results,
        as they can be assigned to any project.

        Args:
            project: The project to check preferences against
            session: The session context

        Returns:
            QuerySet of CustomUser objects who have expressed preferences for
            this session but not for the specified project.
        """
        # Get users who have this project as a preference
        users_with_this_pref = self.with_project_preference(
            project, session
        ).values_list("id", flat=True)

        # Exclude those users, but only include users who have preferences for this session
        return (
            self.exclude(id__in=users_with_this_pref)
            .filter(project_preferences__session=session)
            .distinct()
        )

    def for_comparing_availability(
        self,
        user: "CustomUser",
        session: Optional["Session"] = None,
        session_membership: Optional["SessionMembership"] = None,
    ) -> "QuerySet[CustomUser]":
        """
        Filter users that can be selected for availability comparison.

        Access is determined by:
        - Permission: Users with compare_org_availability see all users
        - Organizer role: Can see all session participants
        - Team member: Can see their team members only

        Args:
            user: The currently logged-in user making the request
            session: Optional session to filter by
            session_membership: Optional session membership for role/team filtering

        Returns:
            QuerySet of CustomUser objects the user can compare availability with
        """
        from home.models import SessionMembership

        qs = self.select_related("profile", "availability").order_by(
            "first_name", "last_name"
        )
        q_filter = Q(availability__isnull=False)

        if session:
            q_filter &= Q(session_memberships__session=session)

        if (
            session_membership
            and session_membership.role != SessionMembership.ORGANIZER
        ):
            q_filter &= Q(session_memberships__team=session_membership.team)
        elif not user.has_perm("home.compare_org_availability"):
            # No session for this user, so check if they can view org-wide availability
            return qs.none()

        return qs.filter(q_filter).distinct()


class CustomUserManager(UserManager.from_queryset(CustomUserQuerySet)):
    pass


class CustomUser(AbstractUser):
    objects = CustomUserManager()

    def __str__(self):
        full_name = self.get_full_name()
        if full_name:
            return f"{self.get_full_name()} ({self.username})"
        return self.username


class UserProfile(models.Model):
    PARTICIPANT = "Participant"
    SPEAKER = "Speaker"
    MENTOR = "Mentor"
    EXPERT = "Expert"
    PROJECT_OWNER = "Project Owner"
    VOLUNTEER = "Volunteer"
    ORGANIZER = "Organizer"
    MEMBER_ROLES = (
        (PARTICIPANT, "Participant"),
        (SPEAKER, "Speaker"),
        (MENTOR, "Mentor"),
        (EXPERT, "Expert"),
        (PROJECT_OWNER, "Project Owner"),
        (VOLUNTEER, "Volunteer"),
        (ORGANIZER, "Organizer"),
    )

    ACTIVE = "active"
    INACTIVE = "inactive"

    MEMBER_STATUS = (
        (ACTIVE, "Active"),
        (INACTIVE, "Inactive"),
    )
    user = DefaultOneToOneField(
        "CustomUser", create=True, on_delete=models.CASCADE, related_name="profile"
    )
    member_status = models.CharField(
        choices=MEMBER_STATUS, default=ACTIVE, max_length=50
    )
    member_role = models.CharField(
        choices=MEMBER_ROLES, default=PARTICIPANT, max_length=50
    )
    pronouns = models.CharField(max_length=20, blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    bio_image = models.ImageField(blank=True, null=True)
    session_participant = models.BooleanField(default=False)
    recruitment_interest = models.BooleanField(default=False)
    accepted_coc = models.BooleanField(default=False)
    email_confirmed = models.BooleanField(default=False)
    receiving_newsletter = models.BooleanField(default=False)
    receiving_event_updates = models.BooleanField(default=False)
    receiving_program_updates = models.BooleanField(default=False)
    github_username = models.CharField(
        max_length=39,
        blank=True,
        null=False,
        default="",
        help_text="Your GitHub username (required for participation)",
    )

    def __str__(self):
        return self.user.username

    def make_token(self):
        return TimestampSigner().sign(self.user.id)

    def check_token(self, token):
        try:
            key = f"{self.user.id}:{token}"
            TimestampSigner().unsign(key, max_age=60 * 60 * 48)  # Valid for 2 days
        except (BadSignature, SignatureExpired):
            return False
        return True


class Link(Orderable):
    member = models.ForeignKey(
        "UserProfile", related_name="links", on_delete=models.CASCADE
    )
    name = models.CharField(max_length=255)
    url = models.URLField(max_length=255)


class MemberList(models.Model):
    name = models.CharField(max_length=255, blank=True, null=True)
    members = models.ManyToManyField("CustomUser", related_name="member_lists")
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)


class UserAvailability(models.Model):
    """
    Stores a user's general weekly availability in UTC.

    Each availability slot is stored as a number representing hours from
    the start of the week (Sunday 00:00 UTC):
    - Range: 0.0 to 167.5 (7 days * 24 hours, in 0.5 hour increments)
    - Format: hours as float

    Examples:
        - Sunday 00:00 UTC = 0.0
        - Monday 00:00 UTC = 24.0
        - Monday 14:30 UTC = 38.5 (24 + 14.5)
        - Saturday 23:30 UTC = 167.5 (6*24 + 23.5)

    The frontend handles timezone conversion from user's local time to UTC.
    """

    user = models.OneToOneField(
        "CustomUser", on_delete=models.CASCADE, related_name="availability"
    )
    # Store availability as an array of floats representing hours from start of week in UTC
    slots = models.JSONField(default=list, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Availability"
        verbose_name_plural = "User Availabilities"

    def __str__(self) -> str:
        return f"{self.user}'s availability"

    def add_slot(self, day: int, hour: float) -> None:
        """
        Add a time slot to availability.

        Args:
            day: Day of week (0=Sunday, 6=Saturday)
            hour: Hour in UTC (0.0-23.5 in 0.5 increments)
        """
        slot_value = (day * 24.0) + hour
        if slot_value not in self.slots:
            self.slots.append(slot_value)
            self.slots.sort()

    def remove_slot(self, day: int, hour: float) -> None:
        """
        Remove a time slot from availability.

        Args:
            day: Day of week (0=Sunday, 6=Saturday)
            hour: Hour in UTC (0.0-23.5 in 0.5 increments)
        """
        slot_value = (day * 24.0) + hour
        if slot_value in self.slots:
            self.slots.remove(slot_value)

    def clear_slots(self) -> None:
        """Clear all availability slots."""
        self.slots = []

    def get_slots_for_day(self, day: int) -> list[float]:
        """
        Get all time slots for a specific day.

        Args:
            day: Day of week (0=Sunday, 6=Saturday)

        Returns:
            List of hours (0.0-23.5) available on that day
        """
        day_start = day * 24.0
        day_end = day_start + 24.0
        day_slots = []
        for slot in self.slots:
            if day_start <= slot < day_end:
                # Return the hour within the day (0.0-23.5)
                day_slots.append(slot - day_start)
        return day_slots

    def get_absolute_url(self):
        return reverse("availability")

    def get_full_url(self):
        return settings.BASE_URL + self.get_absolute_url()


# ====================== Signals =======================
@receiver(post_save, sender=CustomUser)
def create_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)
