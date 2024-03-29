from __future__ import annotations

import datetime

from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from home.managers import SessionMembershipQuerySet
from home.managers import SessionQuerySet


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
    application_survey = models.ForeignKey(
        "home.Survey",
        related_name="application_sessions",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    application_url = models.URLField(
        help_text="This is a URL to the Djangonaut application form. Likely Google Forms.",
        null=True,
        blank=True,
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
        if self.application_survey:
            return self.application_survey.get_survey_response_url()
        return self.application_url

    def get_absolute_url(self):
        return reverse("session_detail", kwargs={"slug": self.slug})

    def get_full_url(self):
        return settings.BASE_URL + self.get_absolute_url()


class SessionMembership(models.Model):
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "session"], name="unique_session_membership"
            )
        ]

    DJANGONAUT = "Djangonaut"
    NAVIGATOR = "Navigator"
    CAPTAIN = "Captain"

    ROLES = (
        (DJANGONAUT, _("Djangonaut")),
        (NAVIGATOR, _("Navigator")),
        (CAPTAIN, _("Mentor")),
    )
    created = models.DateTimeField(auto_now_add=True)
    user = models.ForeignKey(
        "accounts.CustomUser",
        related_name="session_memberships",
        on_delete=models.CASCADE,
    )
    session = models.ForeignKey(
        Session, related_name="session_memberships", on_delete=models.CASCADE
    )
    role = models.CharField(max_length=64, choices=ROLES, default=DJANGONAUT)
    objects = models.Manager.from_queryset(SessionMembershipQuerySet)()
