"""
Tests for editing Discord usernames through the SessionMembership inline
form on the Session admin page (write-through to UserProfile).
"""

from django.test import TestCase

from accounts.factories import UserFactory
from home import constants
from home.factories import SessionFactory, SessionMembershipFactory, TeamFactory
from home.forms import SessionMembershipInlineForm


class SessionMembershipInlineFormTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create()
        cls.team = TeamFactory.create(session=cls.session)
        cls.membership = SessionMembershipFactory.create(
            session=cls.session, team=cls.team, role=constants.DJANGONAUT
        )
        cls.profile = cls.membership.user.profile

    def form_data(self, **overrides):
        data = {
            "session": self.session.pk,
            "user": self.membership.user.pk,
            "team": self.team.pk,
            "role": constants.DJANGONAUT,
            "accepted": "true",
            "discord_username": "",
        }
        data.update(overrides)
        return data

    def test_initial_comes_from_profile(self):
        self.profile.discord_username = "novauser1"
        self.profile.save(update_fields=["discord_username"])

        form = SessionMembershipInlineForm(instance=self.membership)

        self.assertEqual(form.fields["discord_username"].initial, "novauser1")

    def test_save_writes_through_to_profile(self):
        form = SessionMembershipInlineForm(
            data=self.form_data(discord_username="  novauser2  "),
            instance=self.membership,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.discord_username, "novauser2")

    def test_rejects_username_used_by_another_user(self):
        other = UserFactory.create()
        other.profile.discord_username = "taken"
        other.profile.save(update_fields=["discord_username"])

        # Case-insensitive: resolution during setup casefolds usernames.
        form = SessionMembershipInlineForm(
            data=self.form_data(discord_username="TAKEN"),
            instance=self.membership,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("discord_username", form.errors)

    def test_allows_keeping_own_existing_username(self):
        self.profile.discord_username = "novauser1"
        self.profile.save(update_fields=["discord_username"])

        form = SessionMembershipInlineForm(
            data=self.form_data(discord_username="novauser1"),
            instance=self.membership,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_duplicate_check_survives_missing_user(self):
        # An add-flow row with no user selected must not raise while cleaning.
        other = UserFactory.create()
        other.profile.discord_username = "taken"
        other.profile.save(update_fields=["discord_username"])

        form = SessionMembershipInlineForm(
            data=self.form_data(user="", discord_username="taken"),
        )

        self.assertFalse(form.is_valid())
        self.assertIn("user", form.errors)

    def test_save_can_clear_username(self):
        self.profile.discord_username = "novauser1"
        self.profile.save(update_fields=["discord_username"])

        form = SessionMembershipInlineForm(
            data=self.form_data(discord_username=""),
            instance=self.membership,
        )
        # Match the rendered form: initial must be set for changed_data to
        # detect the cleared value, as it is when the admin renders the form.
        form.initial["discord_username"] = "novauser1"

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.discord_username, "")
