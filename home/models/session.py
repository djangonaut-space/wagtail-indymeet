import datetime
from urllib.parse import urlparse

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from home import constants
from home.managers import (
    SessionMembershipQuerySet,
    SessionQuerySet,
    TeamQuerySet,
)
from home.models.base import BaseModel
from home.services.github_stats import Author, TeamScope


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
    description = models.TextField(
        null=False,
        blank=True,
        default="",
        help_text=_("A description or helpful context for prospective contributors."),
    )
    url = models.URLField(
        help_text=_(
            "The URL for the project repository or website. Use the GitHub repo "
            "URL when possible for automated stat tracking."
        ),
    )
    monitor_all_organization_repos = models.BooleanField(
        default=False,
        help_text=_(
            "When enabled, GitHub stats collection searches all source "
            "repositories in this GitHub organization instead of only this "
            "repository."
        ),
    )

    class Meta:
        ordering = ["name"]

    @property
    def github_repo(self) -> tuple[str, str] | None:
        """Return the GitHub org, repo pair from the configured project URL."""
        parsed_url = urlparse(self.url)
        if parsed_url.netloc != "github.com":
            return None

        path_parts = [part for part in parsed_url.path.split("/") if part]
        if len(path_parts) < 2:
            return None

        return path_parts[0], path_parts[1]

    @property
    def github_scope_term(self) -> str | None:
        """Return a GitHub search scope qualifier for this project's repo.

        Returns ``None`` when the project URL is not a GitHub repository.
        """
        github_repo = self.github_repo
        if github_repo is None:
            return None
        owner, repo_name = github_repo
        if self.monitor_all_organization_repos:
            return f"org:{owner}"
        return f"repo:{owner}/{repo_name}"

    def __str__(self) -> str:
        return self.name


class Session(models.Model):
    """Represents a mentoring session / cohort for Djangonaut Space"""

    start_date = models.DateField()
    end_date = models.DateField()
    title = models.CharField(max_length=255)
    short_name = models.CharField(
        max_length=255,
        help_text=_(
            "A short name for the session, e.g. 'Session 1' - without the year."
        ),
    )
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
    discord_invite_url = models.URLField(
        blank=True,
        help_text=_("This should be a newly generated invite to the Discord server."),
    )
    discord_category_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=_(
            "Discord channel category ID for this session, set by the "
            "'Set up Discord' admin action."
        ),
    )
    discord_announcements_channel_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=_(
            "Discord ID of the session-announcements channel, set by the "
            "'Set up Discord' admin action."
        ),
    )
    discord_capnav_channel_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=_(
            "Discord ID of the captains-and-navigators channel, set by the "
            "'Set up Discord' admin action."
        ),
    )
    feedback_form_url = models.URLField(
        blank=True,
        help_text=_(
            "This should be the Program Suggestion Box Google Form from the "
            "session organizer drive folder."
        ),
    )
    djangonauts_have_access = models.BooleanField(
        default=False,
        help_text=_(
            "Whether Djangonauts can access their team detail pages. "
            "Automatically set to True when team welcome emails are sent. "
            "This will be ignored once session start date is in the past."
        ),
    )

    objects = models.Manager.from_queryset(SessionQuerySet)()

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.title

    @property
    def short_name_slug(self) -> str:
        return slugify(self.short_name)

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

        Week boundaries here follow the session's own start weekday, which is
        not necessarily a Monday. Announcement scheduling needs calendar weeks
        instead, so it uses ``week_number_for`` rather than this property.

        Returns:
            Week number if session is current, None if session hasn't started or has ended.
        """
        now = timezone.now().date()
        if now > self.end_date:
            return None
        days_elapsed = (now - self.start_date).days
        return (days_elapsed // 7) + 1

    def week_start_date(self, week_number: int) -> datetime.date:
        """The Monday that opens the given session week.

        Week 1 is the official starting week, so week 0 is the Monday before
        the session begins.
        """
        monday_of_start_week = self.start_date - datetime.timedelta(
            days=self.start_date.weekday()
        )
        return monday_of_start_week + datetime.timedelta(weeks=week_number - 1)

    @property
    def week_one_start(self) -> datetime.date:
        """The Monday of the session's official first week."""
        return self.week_start_date(1)

    def week_number_for(self, post_date: datetime.date) -> int:
        """The session week a calendar date falls in. Inverse of week_start_date."""
        return ((post_date - self.week_one_start).days // 7) + 1

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

    def build_team_scopes(self) -> list[TeamScope]:
        """Build one ``TeamScope`` per team with a GitHub project and djangonauts.

        Teams whose project has no GitHub URL, or whose djangonauts have no
        GitHub username configured, produce no queries and are skipped.
        """
        scopes: list[TeamScope] = []
        for team in self.teams.has_github_project().with_djangonaut_members():
            scope_term = team.project.github_scope_term

            members_by_login: dict[str, Author] = {}
            for membership in team.team_djangonauts:
                github_username = membership.annotated_github_username
                display_name = membership.user.get_full_name() or github_username
                members_by_login[github_username] = Author(
                    github_username=github_username, name=display_name
                )

            if members_by_login:
                scopes.append(
                    TeamScope(
                        scope_term=scope_term,
                        members=tuple(members_by_login.values()),
                        label=str(team),
                    )
                )

        return scopes

    def record_discord_category(self, category_id: str) -> None:
        """Persist the Discord category id, marking this session's Discord active.

        Setup records the category id here; a non-empty value is what
        ``SessionQuerySet.with_active_discord`` treats as the guild-wide Discord
        lock. Paired with ``clear_discord_setup``.
        """
        self.discord_category_id = category_id
        self.save(update_fields=["discord_category_id"])

    def clear_discord_setup(self) -> None:
        """Clear the recorded category so the session is no longer 'active'.

        Teardown archives the channels and frees the program roles, so the
        session no longer holds the guild-wide Discord lock; clearing
        ``discord_category_id`` lets the next session's setup proceed. See
        ``SessionQuerySet.with_active_discord``.
        """
        self.discord_category_id = ""
        self.save(update_fields=["discord_category_id"])


class Team(models.Model):
    # Minimum required overlap hours for team formation
    MIN_NAVIGATOR_MEETING_HOURS = 5
    MIN_CAPTAIN_OVERLAP_HOURS = 3

    objects = models.Manager.from_queryset(TeamQuerySet)()

    class Meta:
        permissions = [
            ("form_team", "Can form teams from the pool of applicants."),
            ("compare_org_availability", "Can compare organization-wide availability."),
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
    discord_channel_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=_(
            "Discord ID of the team's channel, set by the 'Set up Discord' "
            "admin action."
        ),
    )
    discord_voice_channel_id = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text=_(
            "Discord ID of the team's voice channel, set by the 'Set up "
            "Discord' admin action and deleted by teardown."
        ),
    )

    def __str__(self) -> str:
        return f"{self.name} - {self.project.name}"

    def get_absolute_url(self) -> str:
        """Get the URL for the team detail page."""
        return reverse(
            "team_detail", kwargs={"session_slug": self.session.slug, "pk": self.pk}
        )

    def clear_discord_voice_channel(self) -> None:
        """Forget the team's voice channel id after teardown deletes it."""
        self.discord_voice_channel_id = ""
        self.save(update_fields=["discord_voice_channel_id"])


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

    ROLES = (
        (constants.DJANGONAUT, _("Djangonaut")),
        (constants.CAPTAIN, _("Captain")),
        (constants.NAVIGATOR, _("Navigator")),
        (constants.ORGANIZER, _("Organizer")),
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
    role = models.CharField(max_length=64, choices=ROLES, default=constants.DJANGONAUT)
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

    def is_organizer(self) -> bool:
        """Check if this membership has the Organizer role."""
        return self.role == constants.ORGANIZER


class WaitlistQuerySet(models.QuerySet):
    """Custom QuerySet for Waitlist model."""

    def for_admin_site(self, user):
        """Filter to only waitlist entries for sessions the user organizes."""
        if user.is_superuser:
            return self

        return self.filter(
            models.Exists(
                SessionMembership.objects.filter(
                    session=models.OuterRef("session"),
                    user=user,
                    role=constants.ORGANIZER,
                )
            )
        )

    def not_notified(self) -> "WaitlistQuerySet":
        """
        Filter to waitlist entries that have not yet been notified of rejection.

        Returns:
            QuerySet of Waitlist entries where notified_at is null
        """
        return self.filter(notified_at__isnull=True)


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
    notified_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_(
            "When this user was notified of their waitlist rejection. "
            "If set, the user has been sent a rejection notification."
        ),
    )

    objects = models.Manager.from_queryset(WaitlistQuerySet)()

    def __str__(self) -> str:
        return f"{self.user.get_full_name() or self.user.email} - {self.session.title}"
