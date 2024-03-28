from __future__ import annotations

from django.db.models import Exists
from django.db.models import OuterRef
from django.db.models import Value
from django.db.models.query import QuerySet
from django.utils import timezone


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
            return self.annotate(completed_application=Value(False))
        return self.annotate(
            completed_application=Exists(
                UserSurveyResponse.objects.filter(survey=OuterRef("survey"), user=user)
            )
        )


class SessionMembershipQuerySet(QuerySet):
    def _SessionMembership(self):
        return self.model.session._meta.model

    def djangonauts(self):
        return self.filter(role=self._SessionMembership.DJANGONAUT)

    def navigators(self):
        return self.filter(role=self._SessionMembership.NAVIGATOR)

    def captains(self):
        return self.filter(role=self._SessionMembership.CAPTAIN)
