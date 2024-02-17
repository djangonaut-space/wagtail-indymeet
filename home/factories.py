import factory
from home.models import Event, Session


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
