from datetime import timedelta

import factory
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
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
    Testimonial,
    TypeField,
    UserQuestionResponse,
    UserSurveyResponse,
    Waitlist,
    ProjectPreference,
)


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event

    title = factory.Sequence(lambda n: "Event %d" % n)
    slug = factory.Sequence(lambda n: "event-%d" % n)
    start_time = factory.Faker("date_time")
    end_time = factory.Faker("date_time")
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

    start_date = factory.Faker("date_object")
    end_date = factory.Faker("date_object")
    title = factory.Sequence(lambda n: "Session %d" % n)
    slug = factory.Sequence(lambda n: "session-%d" % n)
    invitation_date = factory.Faker("date_object")
    application_start_date = factory.Faker("date_object")
    application_end_date = factory.Faker("date_object")
    application_url = factory.Sequence(lambda n: "https://apply.session%d.com" % n)
    discord_invite_url = "https://discord.gg/test"

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


class OrganizerFactory(factory.django.DjangoModelFactory):
    """Factory that creates a user with organizer role and relevant custom permissions."""

    class Meta:
        model = SessionMembership
        skip_postgeneration_save = True

    user = factory.SubFactory(UserFactory)
    session = factory.SubFactory(SessionFactory)
    team = None
    role = SessionMembership.ORGANIZER
    accepted = True

    @factory.post_generation
    def with_permissions(self, create, extracted, **kwargs):
        if not create:
            return
        # Default to adding permission unless explicitly set to False
        if extracted is False:
            return

        content_type = ContentType.objects.get_for_model(Team)
        permissions = Permission.objects.filter(
            codename__in=["compare_org_availability", "form_team"],
            content_type=content_type,
        )
        self.user.user_permissions.add(*permissions)


class WaitlistFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Waitlist

    user = factory.SubFactory(UserFactory)
    session = factory.SubFactory(SessionFactory)


class TestimonialFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Testimonial

    title = factory.Sequence(lambda n: "Testimonial Title %d" % n)
    text = factory.Sequence(
        lambda n: "This is my testimonial text for my experience during the program. "
        "It was a great learning experience! %d" % n
    )
    author = factory.SubFactory(UserFactory)
    session = factory.SubFactory(SessionFactory)
    is_published = False


class ProjectPreferenceFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ProjectPreference

    user = factory.SubFactory(UserFactory)
    session = factory.SubFactory(SessionFactory)
    project = factory.SubFactory(ProjectFactory)
