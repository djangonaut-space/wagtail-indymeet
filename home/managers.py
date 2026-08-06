from __future__ import annotations

import datetime
from typing import Optional

from django.db.models import (
    Avg,
    Count,
    Exists,
    F,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Value,
)
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from django.utils import timezone

from home import constants


class UserQuestionResponseQuerySet(QuerySet):
    """QuerySet for UserQuestionResponse with filtering methods."""

    def non_sensitive(self):
        """Filter to only responses for non-sensitive questions."""
        return self.filter(question__sensitive=False)

    def for_admin_site(self, user):
        """Filter to only responses for surveys in sessions the user organizes."""
        if user.is_superuser:
            return self

        from home.models import SessionMembership

        return self.filter(
            Exists(
                SessionMembership.objects.filter(
                    session=OuterRef("user_survey_response__survey__session"),
                    user=user,
                    role=constants.ORGANIZER,
                )
            )
        )


class EventQuerySet(QuerySet):
    def published(self):
        return self.filter(is_published=True)

    def upcoming(self):
        return self.filter(start_time__gte=timezone.now())

    def past(self):
        return self.filter(start_time__lte=timezone.now())

    def public(self):
        return self.filter(is_public=True)

    def private(self):
        return self.filter(is_public=False)

    def for_user(self, user):
        """Return events visible to the given user.

        Public events are visible to everyone.
        Private events are only visible to authenticated users with a
        SessionMembership for the event's linked session.
        """
        if user.is_anonymous:
            return self.public()
        return self.filter(
            Q(is_public=True)
            | Q(
                is_public=False,
                session__isnull=False,
                session__session_memberships__user=user,
            )
        ).distinct()


class SessionQuerySet(QuerySet):
    def for_admin_site(self, user):
        """Filter to only sessions the user organizes."""
        if user.is_superuser:
            return self

        from home.models import SessionMembership

        return self.filter(
            Exists(
                SessionMembership.objects.filter(
                    session=OuterRef("pk"), user=user, role=constants.ORGANIZER
                )
            )
        )

    def with_applications(self, user):
        from home.models import UserSurveyResponse

        if user.is_anonymous:
            return self.annotate(annotated_completed_application=Value(False))
        return self.annotate(
            annotated_completed_application=Subquery(
                UserSurveyResponse.objects.filter(
                    survey_id=OuterRef("application_survey_id"), user_id=user.id
                ).values("id")[:1]
            )
        )

    def with_active_discord(self) -> SessionQuerySet:
        """Sessions whose Discord is currently set up (category id recorded).

        Setup records ``discord_category_id`` and teardown clears it, so a
        non-empty value marks a session whose program roles are live on the
        guild. The setup/teardown views use this to enforce a single active
        Discord session at a time — teardown strips program roles guild-wide,
        so overlapping active sessions would cut each other off.
        """
        return self.exclude(discord_category_id="")

    def get_accepting_applications(self) -> Session | None:
        aoe_early_timezone = datetime.timezone(datetime.timedelta(hours=12))
        aoe_late_timezone = datetime.timezone(datetime.timedelta(hours=-12))
        return self.filter(
            application_start_date__lte=timezone.now()
            .astimezone(aoe_early_timezone)
            .date(),
            application_end_date__gte=timezone.now()
            .astimezone(aoe_late_timezone)
            .date(),
        ).first()


class SessionMembershipQuerySet(QuerySet):
    def for_admin_site(self, user):
        """Filter to only memberships for sessions the user organizes."""
        if user.is_superuser:
            return self

        return self.filter(
            Exists(
                self.model.objects.filter(
                    session=OuterRef("session"), user=user, role=constants.ORGANIZER
                )
            )
        )

    def for_session(self, session):
        """Filter memberships for a specific session."""
        return self.filter(session=session)

    def for_team(self, team):
        """Filter memberships for a specific team."""
        return self.filter(team=team)

    def djangonauts(self):
        """Filter to only Djangonauts."""
        return self.filter(role=constants.DJANGONAUT)

    def with_github_username(self):
        """Annotate each membership with its user's configured GitHub username.

        Memberships whose user has no GitHub username configured are excluded,
        so the annotated ``annotated_github_username`` is always a non-empty
        string.
        """
        return self.exclude(user__profile__github_username="").annotate(
            annotated_github_username=F("user__profile__github_username")
        )

    def without_discord_username(self) -> SessionMembershipQuerySet:
        """Filter to memberships whose user has no Discord username configured.

        These are the members the Discord setup/teardown actions can't map to
        a guild member, so the confirmation views surface them for follow-up.
        """
        return self.filter(user__profile__discord_username="")

    def navigators(self):
        """Filter to only Navigators."""
        return self.filter(role=constants.NAVIGATOR)

    def captains(self):
        """Filter to only Captains."""
        return self.filter(role=constants.CAPTAIN)

    def organizers(self):
        """Filter to only Organizers."""
        return self.filter(role=constants.ORGANIZER)

    def enforce_djangonaut_access_control(self) -> SessionMembershipQuerySet:
        """Exclude Djangonaut memberships whose team pages aren't yet accessible.

        Djangonauts can access their team page when the session's
        djangonauts_have_access flag is True or the session start date
        has passed. Non-Djangonaut roles and memberships without teams
        are always included.
        """
        today = timezone.now().date()
        return self.filter(
            ~Q(role=constants.DJANGONAUT)
            | Q(session__djangonauts_have_access=True)
            | Q(session__start_date__lte=today)
        )

    def accepted(self):
        """
        Filter to memberships that are considered accepted/active.

        Only Djangonauts need to explicitly accept their membership.
        Captains, Navigators, and Organizers are automatically members.

        Returns:
            QuerySet of SessionMembership objects that are active members.
        """
        # Djangonauts must have accepted=True
        # All other roles are automatically members (accepted can be None, True, or False)
        return self.filter(
            Q(role=constants.DJANGONAUT, accepted=True)
            | Q(
                role__in=[
                    constants.CAPTAIN,
                    constants.NAVIGATOR,
                    constants.ORGANIZER,
                ]
            )
        )

    def for_user(self, user):
        """
        Filter memberships for a specific user, returning only accepted memberships.

        This combines user filtering with the accepted() logic:
        - For Djangonauts: only returns memberships where accepted=True
        - For other roles: returns all memberships regardless of accepted status

        Args:
            user: The user to filter by

        Returns:
            QuerySet of accepted SessionMembership objects for the user.
        """
        return self.filter(user=user).accepted()


class UserSurveyResponseQuerySet(QuerySet):
    """QuerySet for UserSurveyResponse with team formation filtering."""

    def for_admin_site(self, user):
        """Filter to only responses for surveys in sessions the user organizes."""
        if user.is_superuser:
            return self

        from home.models import SessionMembership

        return self.filter(
            Exists(
                SessionMembership.objects.filter(
                    session=OuterRef("survey__session"),
                    user=user,
                    role=constants.ORGANIZER,
                )
            )
        )

    def for_survey(self, survey):
        """Filter responses for a specific survey."""
        return self.filter(survey=survey)

    def with_previous_application_stats(self, current_survey):
        """
        Annotate responses with previous application statistics.

        Adds:
        - annotated_previous_application_count: Count of applications from previous surveys
        - annotated_previous_avg_score_value: Average score from previous applications
        """
        from home.models import UserSurveyResponse

        # Subquery for previous application count
        # Only count surveys that are application_surveys for sessions
        previous_responses_count = (
            UserSurveyResponse.objects.filter(user=OuterRef("user"))
            .exclude(survey=current_survey)
            .filter(survey__application_session__isnull=False)
            .values("user")
            .annotate(annotated_count=Count("id"))
            .values("annotated_count")
        )

        # Subquery for previous average score
        # Only count surveys that are application_surveys for sessions
        previous_avg_score = (
            UserSurveyResponse.objects.filter(
                user=OuterRef("user"), score__isnull=False
            )
            .exclude(survey=current_survey)
            .filter(survey__application_session__isnull=False)
            .values("user")
            .annotate(annotated_avg_score=Avg("score"))
            .values("annotated_avg_score")
        )

        return self.annotate(
            annotated_previous_application_count=Coalesce(
                Subquery(previous_responses_count), Value(0)
            ),
            annotated_previous_avg_score_value=Subquery(previous_avg_score),
        )

    def with_availability_check(self):
        """
        Annotate responses with availability existence check.

        Adds:
        - annotated_has_availability: Boolean indicating if user has availability
        """
        from accounts.models import UserAvailability

        # Check for users with availability records that have non-empty slots
        # Using slots != '[]' to match PostgreSQL JSONB empty array
        has_availability_subquery = UserAvailability.objects.filter(
            user=OuterRef("user")
        ).exclude(slots=[])

        return self.annotate(
            annotated_has_availability=Exists(has_availability_subquery)
        )

    def with_waitlisted(self, session):
        """
        Annotate the response with the user's waitlist membership.
        """
        from home.models import Waitlist

        return self.annotate(
            annotated_is_waitlisted=Exists(
                session.waitlist_entries.filter(user=OuterRef("user"))
            ),
            annotated_previously_waitlisted=Exists(
                Waitlist.objects.filter(~Q(session=session), user=OuterRef("user"))
            ),
        )

    def with_session_memberships(self, session):
        """
        Prefetch session memberships for a specific session.

        Adds prefetch for user__session_memberships filtered by session.
        """
        from home.models import SessionMembership

        return self.prefetch_related(
            Prefetch(
                "user__session_memberships",
                queryset=SessionMembership.objects.filter(
                    session=session
                ).select_related("team"),
                to_attr="prefetched_current_session_memberships",
            ),
            "user__availability",
        )

    def with_team_assignment(self, team, session):
        """
        Filter responses for users assigned to a specific team in a session.

        Args:
            team: Team instance to filter by
            session: Session instance to filter by
        """
        return self.filter(
            user__session_memberships__session=session,
            user__session_memberships__team=team,
        )

    def without_team_assignment(self, session):
        """
        Filter responses for users without team assignment in a session.

        Args:
            session: Session instance to check for team assignments
        """
        from home.models import SessionMembership

        # Use ~Exists() to filter out users with team assignments
        has_team_assignment = SessionMembership.objects.filter(
            session=session, team__isnull=False, user=OuterRef("user")
        )
        return self.filter(~Exists(has_team_assignment))

    def with_availability_overlap(self, slots: list[float]):
        """
        Filter responses for users with availability overlap with UTC reference slots.

        Args:
            slots: UTC reference slots to check overlap with
        """
        if not slots:
            return self.none()

        from accounts.models import UserAvailability
        from home.availability import local_slot_to_utc_slot

        target_slots = {float(slot) for slot in slots}
        candidate_user_ids = self.order_by().values("user_id").distinct()
        availability_rows = (
            UserAvailability.objects.filter(user_id__in=Subquery(candidate_user_ids))
            .values_list("user_id", "slots", "slots_timezone")
            .iterator(chunk_size=200)
        )

        matching_user_ids = []
        for user_id, availability_slots, timezone_name in availability_rows:
            for slot in availability_slots or []:
                if local_slot_to_utc_slot(float(slot), timezone_name) in target_slots:
                    matching_user_ids.append(user_id)
                    break

        return self.filter(user_id__in=matching_user_ids)

    def with_navigator_overlap(self, team):
        """
        Filter responses for users with availability overlap with team navigators.

        Args:
            team: Team instance whose navigators to check overlap with
        """

        from home.availability import get_user_utc_slots
        from home.models import SessionMembership

        navigator_memberships = (
            SessionMembership.objects.for_team(team)
            .filter(role=constants.NAVIGATOR)
            .select_related("user")
            .prefetch_related("user__availability")
        )
        navigator_slots = set()
        for membership in navigator_memberships:
            navigator_slots.update(get_user_utc_slots(membership.user))

        if not navigator_slots:
            return self.none()
        return self.with_availability_overlap(list(navigator_slots))

    def with_captain_overlap(self, team):
        """
        Filter responses for users with availability overlap with team captain.

        Args:
            team: Team instance whose captain to check overlap with
        """

        from home.availability import get_user_utc_slots
        from home.models import SessionMembership

        captain_memberships = (
            SessionMembership.objects.for_team(team)
            .filter(role=constants.CAPTAIN)
            .select_related("user")
            .prefetch_related("user__availability")
        )
        captain_slots = set()
        for membership in captain_memberships:
            captain_slots.update(get_user_utc_slots(membership.user))

        if not captain_slots:
            return self.none()
        return self.with_availability_overlap(list(captain_slots))

    def with_full_team_formation_data(self, session):
        """
        Annotate responses with all data needed for team formation.

        This is a convenience method that combines multiple annotations.

        Args:
            session: Session instance for context

        Returns:
            QuerySet with annotations:
            - annotated_previous_application_count
            - annotated_previous_avg_score_value
            - annotated_has_availability
            - prefetched session memberships
            - prefetched user availability
            - prefetched project preferences
        """
        from home.models import ProjectPreference

        # Check application_survey_id first to avoid DB hit when not set
        if not session or not session.application_survey_id:
            return self.none()

        # Prefetch project preferences for this session
        project_prefs_prefetch = Prefetch(
            "user__project_preferences",
            queryset=ProjectPreference.objects.for_session(session).select_related(
                "project"
            ),
            to_attr="prefetched_project_preferences",
        )

        return (
            self.for_survey(session.application_survey)
            .select_related("user")
            .with_previous_application_stats(session.application_survey)
            .with_availability_check()
            .with_session_memberships(session)
            .with_waitlisted(session)
            .prefetch_related(project_prefs_prefetch)
        )


class TeamQuerySet(QuerySet):
    """QuerySet for Team with admin filtering."""

    def has_github_project(self):
        """Filter to teams whose project is a GitHub repository.

        Mirrors ``Project.github_repo``: the URL host must be exactly
        ``github.com`` followed by at least an owner and repository. Teams kept
        by this filter are guaranteed a non-``None`` ``github_scope_term``.
        """
        return self.filter(project__url__regex=r"^https?://github\.com/[^/]+/[^/]+")

    def with_djangonaut_members(self):
        """Select each team's project and prefetch its Djangonaut members.

        Only Djangonauts with a configured GitHub username are prefetched, each
        annotated with ``github_username``. The prefetched memberships are
        exposed via the ``team_djangonauts`` attribute on each team.
        """
        from home.models import SessionMembership

        return self.select_related("project").prefetch_related(
            Prefetch(
                "session_memberships",
                queryset=(
                    SessionMembership.objects.djangonauts()
                    .with_github_username()
                    .select_related("user")
                ),
                to_attr="team_djangonauts",
            )
        )

    def for_admin_site(self, user):
        """Filter to only teams for sessions the user organizes."""
        if user.is_superuser:
            return self

        from home.models import SessionMembership

        return self.filter(
            Exists(
                SessionMembership.objects.filter(
                    session=OuterRef("session"),
                    user=user,
                    role=constants.ORGANIZER,
                )
            )
        )


class SurveyQuerySet(QuerySet):
    """QuerySet for Survey with admin filtering."""

    def for_admin_site(self, user):
        """Filter to only surveys for sessions the user organizes."""
        if user.is_superuser:
            return self

        from home.models import SessionMembership

        return self.filter(
            Exists(
                SessionMembership.objects.filter(
                    session=OuterRef("session"),
                    user=user,
                    role=constants.ORGANIZER,
                )
            )
        )


class TestimonialQuerySet(QuerySet):
    """QuerySet for Testimonial with filtering methods."""

    def published(self):
        """Filter to only published testimonials."""
        return self.filter(is_published=True)

    def for_user(self, user):
        """Filter testimonials for a specific user (author)."""
        return self.filter(author=user)

    def for_admin_site(self, user):
        """
        Filter testimonials for admin access.

        Superusers see all testimonials.
        Session organizers see testimonials for their sessions.
        """
        if user.is_superuser:
            return self

        from home.models import SessionMembership

        return self.filter(
            Exists(
                SessionMembership.objects.filter(
                    session=OuterRef("session"),
                    user=user,
                    role=constants.ORGANIZER,
                )
            )
        )
