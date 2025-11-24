from django.db.models import Avg, Count, Exists, OuterRef, Prefetch, Subquery, Value, Q
from django.db.models.functions import Coalesce
from django.db.models.query import QuerySet
from django.utils import timezone


class UserQuestionResponseQuerySet(QuerySet):
    """QuerySet for UserQuestionResponse with filtering methods."""

    def non_sensitive(self):
        """Filter to only responses for non-sensitive questions."""
        return self.filter(question__sensitive=False)


class EventQuerySet(QuerySet):
    def pending(self):
        return self.filter(status=self.model.PENDING)

    def scheduled(self):
        return self.filter(status=self.model.SCHEDULED)

    def canceled(self):
        return self.filter(status=self.model.CANCELED)

    def rescheduled(self):
        return self.filter(status=self.model.RESCHEDULED)

    def visible(self):
        return self.exclude(status=self.model.PENDING)

    def upcoming(self):
        return self.filter(start_time__gte=timezone.now())

    def past(self):
        return self.filter(start_time__lte=timezone.now())


class SessionQuerySet(QuerySet):
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


class SessionMembershipQuerySet(QuerySet):
    def for_session(self, session):
        """Filter memberships for a specific session."""
        return self.filter(session=session)

    def for_team(self, team):
        """Filter memberships for a specific team."""
        return self.filter(team=team)

    def djangonauts(self):
        """Filter to only Djangonauts."""
        return self.filter(role=self.model.DJANGONAUT)

    def navigators(self):
        """Filter to only Navigators."""
        return self.filter(role=self.model.NAVIGATOR)

    def captains(self):
        """Filter to only Captains."""
        return self.filter(role=self.model.CAPTAIN)

    def organizers(self):
        """Filter to only Organizers."""
        return self.filter(role=self.model.ORGANIZER)

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
            Q(role=self.model.DJANGONAUT, accepted=True)
            | Q(
                role__in=[
                    self.model.CAPTAIN,
                    self.model.NAVIGATOR,
                    self.model.ORGANIZER,
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
        return self.annotate(
            annotated_is_waitlisted=Exists(
                session.waitlist_entries.filter(user=OuterRef("user"))
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
        Filter responses for users with availability overlap with given slots.

        Args:
            slots: List of time slots to check overlap with
        """
        if not slots:
            return self.none()
        return self.filter(user__availability__slots__has_overlap=slots)

    def with_navigator_overlap(self, team):
        """
        Filter responses for users with availability overlap with team navigators.

        Args:
            team: Team instance whose navigators to check overlap with
        """
        from home.models import SessionMembership
        from home.availability import get_role_slots

        navigator_slots = get_role_slots(team, role=SessionMembership.NAVIGATOR)
        if not navigator_slots:
            return self.none()
        return self.with_availability_overlap(navigator_slots)

    def with_captain_overlap(self, team):
        """
        Filter responses for users with availability overlap with team captain.

        Args:
            team: Team instance whose captain to check overlap with
        """
        from home.models import SessionMembership
        from home.availability import get_role_slots

        captain_slots = get_role_slots(team, role=SessionMembership.CAPTAIN)
        if not captain_slots:
            return self.none()
        return self.with_availability_overlap(captain_slots)

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
