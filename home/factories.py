from datetime import timedelta

import factory
from django.utils import timezone

from accounts.factories import UserFactory
from home.models import (
    Event,
    Project,
    Question,
    ResourceLink,
    Session,
    SessionMembership,
    Survey,
    Team,
    TypeField,
    UserQuestionResponse,
    UserSurveyResponse,
    Waitlist,
)


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event

    title = factory.Sequence(lambda n: "Event %d" % n)
    slug = factory.Sequence(lambda n: "event-%d" % n)
    start_time = factory.Faker("datetime")
    end_time = factory.Faker("datetime")
    location = "https://zoom.link"
    status = Event.SCHEDULED


class ResourceLinkFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ResourceLink

    path = factory.Sequence(lambda n: "path/resource-%d" % n)
    url = factory.Sequence(lambda n: "https://testserver/%d/resource" % n)


class SessionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Session

    start_date = factory.Faker("date")
    end_date = factory.Faker("date")
    title = factory.Sequence(lambda n: "Session %d" % n)
    slug = factory.Sequence(lambda n: "session-%d" % n)
    invitation_date = factory.Faker("date")
    application_start_date = factory.Faker("date")
    application_end_date = factory.Faker("date")
    application_url = factory.Sequence(lambda n: "https://apply.session%d.com" % n)

    @classmethod
    def create_active(cls, survey) -> Session:
        """Create an active session for a given survey."""
        today = timezone.now().date()
        return SessionFactory.create(
            application_survey=survey,
            application_start_date=today - timedelta(days=1),
            application_end_date=today + timedelta(days=10),
        )


class SurveyFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Survey

    name = factory.Sequence(lambda n: "Survey %d" % n)


class QuestionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Question

    survey = factory.SubFactory(SurveyFactory)
    label = factory.Sequence(lambda n: "Label %d" % n)
    type_field = TypeField.TEXT


class UserSurveyResponseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserSurveyResponse

    user = factory.SubFactory(UserFactory)
    survey = factory.SubFactory(SurveyFactory)


class UserQuestionResponseFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserQuestionResponse

    question = factory.SubFactory(QuestionFactory)
    value = factory.Sequence(lambda n: "Answer %d" % n)
    user_survey_response = factory.SubFactory(UserSurveyResponseFactory)


class ProjectFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Project

    name = factory.Sequence(lambda n: "Project %d" % n)
    url = factory.Sequence(lambda n: "https://github.com/project-%d" % n)


class TeamFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Team

    session = factory.SubFactory(SessionFactory)
    name = factory.Sequence(lambda n: "Team %d" % n)
    project = factory.SubFactory(ProjectFactory)


class SessionMembershipFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = SessionMembership

    user = factory.SubFactory(UserFactory)
    session = factory.SubFactory(SessionFactory)
    team = factory.SubFactory(TeamFactory)
    role = SessionMembership.DJANGONAUT


class WaitlistFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Waitlist

    user = factory.SubFactory(UserFactory)
    session = factory.SubFactory(SessionFactory)
