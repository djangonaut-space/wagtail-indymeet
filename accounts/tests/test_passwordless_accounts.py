"""
Tests for accounts that have no password, as when someone signs up with GitHub.

Wherever the site would ask for the current password, these users confirm it is
them with a code sent to their email instead.
"""

from unittest.mock import patch

from django.contrib.auth import SESSION_KEY
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse

from accounts.forms import DeleteAccountForm
from accounts.tests.two_factor_helpers import create_user
from accounts.tests.two_factor_helpers import PASSWORD
from accounts.tests.two_factor_helpers import reauthenticate_by_code

DELETE_URL = "/accounts/delete/"
SET_PASSWORD_URL = "/accounts/password/set/"
CHANGE_PASSWORD_URL = "/accounts/password_change/"
REQUEST_CODE_URL = "/accounts/reauthenticate/code/"
NEW_PASSWORD = "a-brand-new-passphrase"


@override_settings(ENVIRONMENT="production")
class PasswordlessTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = create_user()
        self.user.set_unusable_password()
        self.user.save()
        self.client.force_login(self.user)


class DeleteAccountWithoutPasswordTests(PasswordlessTestCase):
    def test_urls(self):
        self.assertEqual(reverse("delete_account"), DELETE_URL)
        self.assertEqual(reverse("account_set_password"), SET_PASSWORD_URL)
        self.assertEqual(reverse("password_change"), CHANGE_PASSWORD_URL)
        self.assertEqual(reverse("account_change_password"), CHANGE_PASSWORD_URL)

    def test_page_asks_for_an_emailed_code_first(self):
        response = self.client.get(DELETE_URL)

        self.assertRedirects(
            response,
            f"{REQUEST_CODE_URL}?next={DELETE_URL}",
            fetch_redirect_response=False,
        )

    @patch("accounts.views.delete_user_account")
    def test_deleting_without_the_code_is_refused(self, task):
        response = self.client.post(DELETE_URL)

        self.assertIn(REQUEST_CODE_URL, response.url)
        task.enqueue.assert_not_called()

    def test_page_has_no_password_field_after_the_code(self):
        reauthenticate_by_code(self.client)

        response = self.client.get(DELETE_URL)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'type="password"')
        self.assertContains(response, "You confirmed it is you")

    @patch("accounts.views.delete_user_account")
    def test_account_is_deleted_after_the_code(self, task):
        reauthenticate_by_code(self.client)

        response = self.client.post(DELETE_URL)

        self.assertRedirects(response, reverse("login"))
        task.enqueue.assert_called_once_with(user_id=self.user.id)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_form_has_no_password_field_without_a_password(self):
        form = DeleteAccountForm(data={}, user=self.user)

        self.assertNotIn("password", form.fields)
        self.assertTrue(form.is_valid())

    @patch("accounts.views.delete_user_account")
    def test_user_with_a_password_is_still_asked_for_it(self, task):
        self.user.set_password(PASSWORD)
        self.user.save()
        self.client.force_login(self.user)

        page = self.client.get(DELETE_URL)
        response = self.client.post(DELETE_URL, {"password": "wrong"})

        self.assertContains(page, 'type="password"')
        self.assertContains(response, "Incorrect password")
        task.enqueue.assert_not_called()


class SetPasswordTests(PasswordlessTestCase):
    def test_change_password_link_leads_to_setting_one(self):
        response = self.client.get(CHANGE_PASSWORD_URL)

        self.assertRedirects(response, SET_PASSWORD_URL, fetch_redirect_response=False)

    def test_setting_a_password_asks_for_an_emailed_code_first(self):
        response = self.client.post(
            SET_PASSWORD_URL, {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD}
        )

        self.assertIn(REQUEST_CODE_URL, response.url)
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_page_uses_the_site_layout(self):
        reauthenticate_by_code(self.client)

        response = self.client.get(SET_PASSWORD_URL)

        self.assertTemplateUsed(response, "base.html")
        self.assertContains(response, "Set Password")

    def test_password_can_be_set_after_the_code(self):
        reauthenticate_by_code(self.client)
        mail.outbox.clear()

        response = self.client.post(
            SET_PASSWORD_URL, {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD}
        )

        self.assertRedirects(response, reverse("profile"))
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertIn("Password Set", mail.outbox[0].subject)

    def test_mismatched_passwords_are_rejected(self):
        reauthenticate_by_code(self.client)

        response = self.client.post(
            SET_PASSWORD_URL, {"password1": NEW_PASSWORD, "password2": "different"}
        )

        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())

    def test_user_with_a_password_is_sent_to_change_it(self):
        self.user.set_password(PASSWORD)
        self.user.save()
        self.client.force_login(self.user)

        response = self.client.get(SET_PASSWORD_URL)
        page = self.client.get(CHANGE_PASSWORD_URL)

        self.assertRedirects(
            response, CHANGE_PASSWORD_URL, fetch_redirect_response=False
        )
        self.assertContains(page, "old_password")

    def test_unconfirmed_email_cannot_receive_a_code(self):
        self.user.profile.email_confirmed = False
        self.user.profile.save()

        self.assertEqual(self.client.get(SET_PASSWORD_URL).status_code, 403)
        self.assertEqual(self.client.get(DELETE_URL).status_code, 403)
