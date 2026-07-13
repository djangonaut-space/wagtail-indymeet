import factory

from accounts.factories import UserFactory
from availability.models import UserAvailability


class UserAvailabilityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserAvailability

    user = factory.SubFactory(UserFactory)
    slots = []
