"""Tests for keeping allauth's EmailAddress in step with email confirmation."""

import re
from importlib import import_module

from allauth.account.models import EmailAddress
from django.apps import apps
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse

from accounts.factories import UserFactory
from accounts.models import CustomUser
from accounts.tests.two_factor_helpers import create_user
from accounts.tests.two_factor_helpers import current_code
from accounts.two_factor import has_two_factor

migration = import_module(
    "accounts.migrations.0022_mirror_email_confirmation_to_allauth"
)


def addresses() -> list[tuple[str, bool, bool]]:
    return list(
        EmailAddress.objects.order_by("email").values_list(
            "email", "verified", "primary"
        )
    )


class MirrorEmailConfirmationTests(TestCase):
    def test_new_user_has_no_email_address_until_their_profile_is_saved(self):
        user = CustomUser.objects.create_user("new", "new@example.com", "password")

        self.assertEqual(addresses(), [])

        user.profile.save()

        self.assertEqual(addresses(), [("new@example.com", False, True)])

    def test_confirming_the_email_marks_it_verified(self):
        user = create_user(email="Astronaut@Example.com")

        self.assertEqual(addresses(), [("astronaut@example.com", True, True)])

        user.profile.email_confirmed = False
        user.profile.save()

        self.assertEqual(addresses(), [("astronaut@example.com", False, True)])

    def test_changing_the_email_replaces_the_address(self):
        user = create_user()
        user.email = "new@example.com"
        user.save()
        user.profile.email_confirmed = False
        user.profile.save()

        self.assertEqual(addresses(), [("new@example.com", False, True)])

    def test_user_without_an_email_has_no_address(self):
        user = create_user()
        user.email = ""
        user.save()
        user.profile.save()

        self.assertEqual(addresses(), [])

    def test_out_of_date_address_of_another_user_is_dropped(self):
        """An address freed by one user can be confirmed by the next."""
        first = create_user("first", email="shared@example.com")
        CustomUser.objects.filter(pk=first.pk).update(email="first@example.com")

        second = create_user("second", email="shared@example.com")

        self.assertEqual(
            list(EmailAddress.objects.values_list("user", "email", "verified")),
            [(second.pk, "shared@example.com", True)],
        )

    def test_fixtures_are_not_mirrored(self):
        user = create_user()
        EmailAddress.objects.all().delete()

        user.profile.save_base(raw=True)

        self.assertEqual(addresses(), [])


class BackfillMigrationTests(TestCase):
    def test_existing_users_get_an_address_matching_their_profile(self):
        confirmed = UserFactory.create(email="Confirmed@example.com")
        confirmed.profile.email_confirmed = True
        UserFactory.create(email="unconfirmed@example.com")
        UserFactory.create(email="")
        CustomUser.objects.filter(pk=confirmed.pk).update(email="Confirmed@example.com")
        confirmed.profile.__class__.objects.filter(user=confirmed).update(
            email_confirmed=True
        )

        migration.create_email_addresses(apps, None)

        self.assertEqual(
            addresses(),
            [
                ("confirmed@example.com", True, True),
                ("unconfirmed@example.com", False, True),
            ],
        )

    def test_running_again_changes_nothing(self):
        create_user()

        migration.create_email_addresses(apps, None)

        self.assertEqual(addresses(), [("astronaut@example.com", True, True)])


@override_settings(ENVIRONMENT="production")
class PasswordlessUserTests(TestCase):
    """Someone who signed up with GitHub has no password to confirm changes with."""

    def test_two_factor_can_be_set_up_with_an_emailed_code(self):
        cache.clear()
        user = create_user()
        user.set_unusable_password()
        user.save()
        self.client.force_login(user)
        activate_url = reverse("mfa_activate_totp")
        request_code_url = reverse("account_request_reauthentication_code")

        response = self.client.get(activate_url)
        self.assertRedirects(
            response,
            f"{request_code_url}?next={activate_url}",
            fetch_redirect_response=False,
        )
        page = self.client.get(response.url)
        self.assertTemplateUsed(page, "base.html")
        recipient = page.context["form"].fields["recipient"].choices[0][0]
        self.client.post(response.url, {"recipient": recipient})
        self.assertEqual(mail.outbox[0].to, [user.email])
        code = re.search(r"^\S+-\S+$", mail.outbox[0].body, re.MULTILINE).group()
        self.client.post(
            reverse("account_confirm_reauthentication_code"), {"code": code}
        )

        response = self.client.get(activate_url)
        self.assertEqual(response.status_code, 200)
        self.client.post(
            activate_url, {"code": current_code(response.context["form"].secret)}
        )
        self.assertTrue(has_two_factor(user))
