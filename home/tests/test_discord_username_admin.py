"""
Tests for linking Discord members through the SessionMembership inline
form on the Session admin page (write-through to UserProfile).
"""

from django.test import TestCase

from accounts.factories import UserFactory
from home import constants
from home.factories import (
    DiscordMemberFactory,
    SessionFactory,
    SessionMembershipFactory,
    TeamFactory,
)
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
        cls.member = DiscordMemberFactory.create(discord_id="100", username="novauser1")
        cls.other_member = DiscordMemberFactory.create(
            discord_id="101", username="novauser2"
        )

    def form_data(self, **overrides):
        data = {
            "session": self.session.pk,
            "user": self.membership.user.pk,
            "team": self.team.pk,
            "role": constants.DJANGONAUT,
            "accepted": "true",
            "discord_member": "",
        }
        data.update(overrides)
        return data

    def test_initial_comes_from_profile(self):
        self.profile.discord_member = self.member
        self.profile.save(update_fields=["discord_member"])

        form = SessionMembershipInlineForm(instance=self.membership)

        self.assertEqual(form.fields["discord_member"].initial, self.member)

    def test_save_writes_through_to_profile(self):
        form = SessionMembershipInlineForm(
            data=self.form_data(discord_member=self.other_member.pk),
            instance=self.membership,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.profile.refresh_from_db()
        self.assertEqual(self.profile.discord_member_id, self.other_member.pk)

    def test_rejects_member_linked_to_another_user(self):
        other = UserFactory.create()
        other.profile.discord_member = self.member
        other.profile.save(update_fields=["discord_member"])

        form = SessionMembershipInlineForm(
            data=self.form_data(discord_member=self.member.pk),
            instance=self.membership,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("discord_member", form.errors)

    def test_allows_keeping_own_existing_member(self):
        self.profile.discord_member = self.member
        self.profile.save(update_fields=["discord_member"])

        form = SessionMembershipInlineForm(
            data=self.form_data(discord_member=self.member.pk),
            instance=self.membership,
        )

        self.assertTrue(form.is_valid(), form.errors)

    def test_queryset_excludes_members_linked_to_other_users(self):
        """A member already linked to another user shouldn't be selectable."""
        other = UserFactory.create()
        other.profile.discord_member = self.other_member
        other.profile.save(update_fields=["discord_member"])

        form = SessionMembershipInlineForm(instance=self.membership)

        self.assertNotIn(self.other_member, form.fields["discord_member"].queryset)

    def test_queryset_includes_own_linked_member(self):
        """The member already linked to this instance's user stays selectable."""
        self.profile.discord_member = self.member
        self.profile.save(update_fields=["discord_member"])

        form = SessionMembershipInlineForm(instance=self.membership)

        self.assertIn(self.member, form.fields["discord_member"].queryset)

    def test_save_can_clear_member(self):
        self.profile.discord_member = self.member
        self.profile.save(update_fields=["discord_member"])

        form = SessionMembershipInlineForm(
            data=self.form_data(discord_member=""),
            instance=self.membership,
        )
        form.initial["discord_member"] = self.member.pk

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.discord_member)
