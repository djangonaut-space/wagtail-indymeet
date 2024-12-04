import factory

from accounts.factories import UserFactory
from home.models import Event
from home.models import Question
from home.models import Session
from home.models import Survey
from home.models import TypeField
from home.models import UserQuestionResponse
from home.models import UserSurveyResponse


class EventFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Event

    title = factory.Sequence(lambda n: "Event %d" % n)
    slug = factory.Sequence(lambda n: "event-%d" % n)
    start_time = factory.Faker("datetime")
    end_time = factory.Faker("datetime")
    location = "https://zoom.link"
    status = Event.SCHEDULED


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
