import factory

from accounts.factories import UserFactory
from availability.models import CalendarConnection, UserAvailability


class UserAvailabilityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserAvailability

    user = factory.SubFactory(UserFactory)
    slots = []


class CalendarConnectionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CalendarConnection

    user = factory.SubFactory(UserFactory)
    account_label = factory.LazyAttribute(lambda obj: f"{obj.user.email}")
    access_token = "test-access-token"
    refresh_token = "test-refresh-token"
