import factory
from django.db.models.signals import post_save

from accounts.models import CustomUser, UserAvailability, UserProfile


@factory.django.mute_signals(post_save)
class ProfileFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserProfile

    user = factory.SubFactory("accounts.factories.UserFactory", profile=None)


@factory.django.mute_signals(post_save)
class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = CustomUser
        skip_postgeneration_save = True

    username = factory.Sequence(lambda n: "user_%d" % n)
    first_name = "Jane"
    last_name = "Doe"
    email = factory.LazyAttribute(lambda obj: f"{obj.username}@example.com")
    profile = factory.RelatedFactory(ProfileFactory, factory_related_name="user")


class UserAvailabilityFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = UserAvailability

    user = factory.SubFactory(UserFactory)
    slots = []
