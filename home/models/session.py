import datetime

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from home.managers import SessionMembershipQuerySet, SessionQuerySet


class Project(models.Model):
    """
    Represents a project that teams can work on.

    Projects are standalone entities that can be associated with multiple sessions,
    allowing applicants to indicate their project preferences during application.
    """

    name = models.CharField(
        max_length=255,
        unique=True,
        help_text=_("The name of the project (e.g., 'Django', 'Wagtail')"),
    )
    url = models.URLField(
        help_text=_("The URL for the project repository or website"),
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Session(models.Model):
    """Represents a mentoring session / cohort for Djangonaut Space"""

    start_date = models.DateField()
    end_date = models.DateField()
    title = models.CharField(max_length=255)
    slug = models.SlugField(
        help_text="This is used in the URL to identify the session.", unique=True
    )
    description = models.TextField(blank=True, null=True)
    # This gives you the users who are participants. If you want to find
    # the users who have a specific role, you'll need to use SessionMembership
    participants = models.ManyToManyField(
        "accounts.CustomUser",
        through="SessionMembership",
        related_name="sessions",
        blank=True,
    )
    invitation_date = models.DateField(
        help_text="This is the date when the first round of Djangonaut invitations "
        "will be sent out."
    )
    application_start_date = models.DateField(
        help_text="This is the start date for Djangonaut applications."
    )
    application_end_date = models.DateField(
        help_text="This is the end date for Djangonaut applications."
    )
    application_survey = models.OneToOneField(
        "home.Survey",
        related_name="application_session",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    application_url = models.URLField(
        help_text="This is a URL to the Djangonaut application form. Likely Google Forms.",
        null=True,
        blank=True,
    )
    available_projects = models.ManyToManyField(
        Project,
        related_name="sessions",
        blank=True,
        help_text=_("Projects available for selection during this session"),
    )
    results_notifications_sent_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_(
            "Timestamp when application result notifications "
            "(accepted/waitlist/rejected) were queued for delivery. "
            "Note: This marks when tasks were enqueued, not when all emails completed."
        ),
    )

    objects = models.Manager.from_queryset(SessionQuerySet)()

    def __str__(self):
        return self.title

    def application_start_anywhere_on_earth(self):
        aoe_early_timezone = datetime.timezone(datetime.timedelta(hours=12))
        return datetime.datetime.combine(
            self.application_start_date,
            datetime.datetime.min.time(),
            tzinfo=aoe_early_timezone,
        )

    def application_end_anywhere_on_earth(self):
        aoe_late_timezone = datetime.timezone(datetime.timedelta(hours=-12))
        return datetime.datetime.combine(
            self.application_end_date,
            datetime.datetime.max.time(),
            tzinfo=aoe_late_timezone,
        )

    def is_accepting_applications(self):
        """Determine if the current date is within the application window"""
        return (
            self.application_start_anywhere_on_earth()
            <= timezone.now()
            <= self.application_end_anywhere_on_earth()
        )

    def get_application_url(self):
        # Check application_survey_id first to avoid DB hit when not set
        if self.application_survey_id:
            return self.application_survey.get_survey_response_url()
        return self.application_url

    def get_absolute_url(self):
        return reverse("session_detail", kwargs={"slug": self.slug})

    def get_full_url(self):
        return settings.BASE_URL + self.get_absolute_url()

    def is_current_or_upcoming(self) -> bool:
        """Check if the session is currently active or upcoming (before end dates)."""
        return timezone.now().date() <= self.end_date

    @property
    def current_week(self) -> int | None:
        """
        Get the current week number of the session (1-indexed).

        Returns:
            Week number if session is current, None if session hasn't started or has ended.
        """
        now = timezone.now().date()
        if now > self.end_date:
            return None
        days_elapsed = (now - self.start_date).days
        return (days_elapsed // 7) + 1

    @property
    def status(self) -> str:
        """
        Get the current status of the session.

        Returns:
            'current', 'upcoming', or 'past'
        """
        now = timezone.now().date()
        if now < self.start_date:
            return "upcoming"
        elif now > self.end_date:
            return "past"
        else:
            return "current"


class Team(models.Model):
    # Minimum required overlap hours for team formation
    MIN_NAVIGATOR_MEETING_HOURS = 5
    MIN_CAPTAIN_OVERLAP_HOURS = 3

    class Meta:
        permissions = [
            ("form_team", "Can form teams from the pool of applicants."),
        ]

    session = models.ForeignKey(Session, related_name="teams", on_delete=models.CASCADE)
    name = models.CharField()
    project = models.ForeignKey(
        Project,
        related_name="teams",
        on_delete=models.PROTECT,
        help_text=_("The project the team is working on."),
    )
    google_drive_folder = models.URLField(
        blank=True,
        null=True,
        help_text=_("Link to the team's Google Drive folder with workbooks"),
    )

    def __str__(self) -> str:
        return f"{self.name} - {self.project.name}"

    def get_absolute_url(self) -> str:
        """Get the URL for the team detail page."""
        return reverse(
            "team_detail", kwargs={"session_slug": self.session.slug, "pk": self.pk}
        )


class ProjectPreferenceQuerySet(models.QuerySet):
    """Custom QuerySet for ProjectPreference model."""

    def for_user_session(
        self, user: "CustomUser", session: "Session"
    ) -> "ProjectPreferenceQuerySet":
        """
        Filter preferences for a specific user and session.

        Args:
            user: The user to filter by
            session: The session to filter by

        Returns:
            QuerySet of ProjectPreference objects for this user/session combination
        """
        return self.filter(user=user, session=session)

    def for_session(self, session: "Session") -> "ProjectPreferenceQuerySet":
        """
        Filter preferences for a specific session.

        Args:
            session: The session to filter by

        Returns:
            QuerySet of ProjectPreference objects for this session
        """
        return self.filter(session=session)


class ProjectPreference(models.Model):
    """
    Represents a user's project preferences for a session application.

    Users can indicate which projects they prefer to work on during application.
    If no preferences exist, the user is okay with any project.
    """

    user = models.ForeignKey(
        "accounts.CustomUser",
        related_name="project_preferences",
        on_delete=models.CASCADE,
        # Index comes from unique_project_preference
        db_index=False,
    )
    session = models.ForeignKey(
        Session,
        related_name="project_preferences",
        on_delete=models.CASCADE,
    )
    project = models.ForeignKey(
        Project,
        related_name="preferences",
        on_delete=models.CASCADE,
    )

    objects = models.Manager.from_queryset(ProjectPreferenceQuerySet)()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "session", "project"], name="unique_project_preference"
            )
        ]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.project.name} ({self.session.title})"


class SessionMembership(models.Model):
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "user"], name="unique_session_membership"
            )
        ]

    DJANGONAUT = "Djangonaut"
    CAPTAIN = "Captain"
    NAVIGATOR = "Navigator"
    ORGANIZER = "Organizer"

    ROLES = (
        (DJANGONAUT, _("Djangonaut")),
        (CAPTAIN, _("Captain")),
        (NAVIGATOR, _("Navigator")),
        (ORGANIZER, _("Organizer")),
    )
    created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        "accounts.CustomUser",
        related_name="session_memberships",
        on_delete=models.CASCADE,
    )
    session = models.ForeignKey(
        Session,
        related_name="session_memberships",
        on_delete=models.CASCADE,
        # Index is covered by unique_session_membership
        db_index=False,
    )
    team = models.ForeignKey(
        Team,
        null=True,
        blank=True,
        related_name="session_memberships",
        on_delete=models.CASCADE,
    )
    role = models.CharField(max_length=64, choices=ROLES, default=DJANGONAUT)
    accepted = models.BooleanField(
        null=True,
        blank=True,
        help_text=_(
            "Whether the user has accepted their session membership. "
            "None = not yet responded, True = accepted, False = declined"
        ),
    )
    acceptance_deadline = models.DateField(
        null=True,
        blank=True,
        help_text=_("Deadline for the user to accept their session membership"),
    )
    accepted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_("Timestamp when the user accepted their session membership"),
    )
    objects = models.Manager.from_queryset(SessionMembershipQuerySet)()


class Waitlist(models.Model):
    """
    Represents users who are waitlisted for a session.

    Waitlisted users are applicants who are not outright rejected but also
    not yet accepted into the session. They exist in a state between
    application and acceptance, and may be promoted to SessionMembership
    if space becomes available.
    """

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["session", "user"], name="unique_waitlist_entry"
            )
        ]
        ordering = ["created_at"]
        verbose_name = _("Waitlist Entry")
        verbose_name_plural = _("Waitlist Entries")

    user = models.ForeignKey(
        "accounts.CustomUser",
        related_name="waitlist_entries",
        on_delete=models.CASCADE,
        help_text=_("The user who is waitlisted for this session"),
    )
    session = models.ForeignKey(
        Session,
        related_name="waitlist_entries",
        on_delete=models.CASCADE,
        help_text=_("The session the user is waitlisted for"),
        # Index is covered by unique_waitlist_entry
        db_index=False,
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text=_("When this user was added to the waitlist"),
    )

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.email} - {self.session.title}"
