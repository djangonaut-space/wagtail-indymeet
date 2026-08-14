import factory
from django.conf import settings
from django.db.models.signals import post_save

from accounts.models import (
    CustomUser,
    DiscordMember,
    DiscordRole,
    UserAvailability,
    UserProfile,
)


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
    slots_timezone = factory.LazyFunction(lambda: settings.TIME_ZONE)


class DiscordRoleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DiscordRole

    name = factory.Sequence(lambda n: "Role %d" % n)
    discord_id = factory.Sequence(lambda n: "role-id-%d" % n)


class DiscordMemberFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = DiscordMember

    discord_id = factory.Sequence(lambda n: "member-id-%d" % n)
    username = factory.Sequence(lambda n: "discorduser%d" % n)
