"""
Tests for the Discord setup/teardown/team-messages admin views.

POST tests run the real orchestration against the stubbed Discord API from
home.tests.discord.stubs — the immediate task backend executes the enqueued
background task during the request — so these focus on permissions,
confirmation pages, the redirect, and the emailed report. The orchestration
internals are covered in test_session_service.
"""

import responses as rsps
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse

from accounts.factories import UserFactory
from home import constants
from home.factories import (
    OrganizerFactory,
    SessionFactory,
    SessionMembershipFactory,
    TeamFactory,
)
from home.tests.discord.stubs import (
    GUILD_URL,
    STANDING_GUILD_ROLES,
    stub_discord_api,
)


@override_settings(ALLOWED_EMAILS_FOR_TESTING=["admin@example.com"])
class DiscordViewsTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = UserFactory.create(
            username="admin", is_staff=True, is_superuser=True
        )
        cls.session = SessionFactory.create(
            title="Session 4", short_name="Session 4", discord_category_id="cat-1"
        )
        cls.team = TeamFactory.create(session=cls.session, name="Bee")
        cls.membership = SessionMembershipFactory.create(
            session=cls.session, team=cls.team, role=constants.DJANGONAUT
        )

    def setUp(self):
        self.client.force_login(self.admin_user)


class DiscordSetupViewTests(DiscordViewsTestCase):
    def url(self):
        return reverse("admin:session_discord_setup", args=[self.session.id])

    def test_get_renders_confirmation_with_missing_usernames(self):
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/discord_setup.html")
        self.assertContains(response, "Set up Discord - Session 4")
        # The factory user has no discord username, so they're flagged.
        self.assertContains(
            response,
            self.membership.user.get_full_name() or self.membership.user.username,
        )

    @rsps.activate
    def test_post_runs_setup_and_emails_report(self):
        stub_discord_api(roles=STANDING_GUILD_ROLES + [{"id": "r-bee", "name": "Bee"}])

        response = self.client.post(self.url())

        self.assertRedirects(response, reverse("admin:home_session_changelist"))
        # The immediate task backend ran the orchestration during the request.
        self.session.refresh_from_db()
        self.team.refresh_from_db()
        self.assertNotEqual(self.team.discord_channel_id, "")
        self.assertNotEqual(self.session.discord_capnav_channel_id, "")

        self.assertEqual(len(mail.outbox), 1)
        email_message = mail.outbox[0]
        self.assertEqual(email_message.to, ["admin@example.com"])
        self.assertIn("Discord setup complete", email_message.subject)
        self.assertIn("team-bee", email_message.body)
        # The report links to the page that generates the team messages.
        team_messages_url = reverse(
            "admin:session_discord_team_messages", args=[self.session.id]
        )
        self.assertIn(f"https://example.com{team_messages_url}", email_message.body)
        # The member without a discord username is listed for follow-up.
        self.assertIn("Jane Doe", email_message.body)
        # No errors, so no superusers are CCed.
        self.assertEqual(email_message.cc, [])

    @override_settings(
        ALLOWED_EMAILS_FOR_TESTING=["admin@example.com", "other-admin@example.com"]
    )
    @rsps.activate
    def test_post_api_error_is_reported_in_email_and_ccs_superusers(self):
        other_admin = UserFactory.create(username="other-admin", is_superuser=True)
        rsps.add(rsps.GET, f"{GUILD_URL}/roles", status=403)

        response = self.client.post(self.url())

        self.assertRedirects(response, reverse("admin:home_session_changelist"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Discord API error", mail.outbox[0].body)
        # Superusers are CCed on errors; the requester isn't CCed twice.
        self.assertEqual(mail.outbox[0].cc, [other_admin.email])

    @override_settings(DISCORD_BOT_TOKEN="", DISCORD_GUILD_ID="")
    @rsps.activate
    def test_disabled_integration_redirects(self):
        response = self.client.get(self.url(), follow=True)

        self.assertRedirects(response, reverse("admin:home_session_changelist"))
        self.assertEqual(len(rsps.calls), 0)
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("not configured" in m for m in messages))

    def test_non_organizer_staff_gets_404(self):
        outsider = UserFactory.create(username="outsider", is_staff=True)
        self.client.force_login(outsider)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 404)

    def test_organizer_of_session_has_access(self):
        organizer = OrganizerFactory.create(
            session=self.session, with_permissions=False
        )
        organizer.user.is_staff = True
        organizer.user.save(update_fields=["is_staff"])
        self.client.force_login(organizer.user)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)

    def test_blocked_when_another_session_has_discord_active(self):
        SessionFactory.create(title="Other", discord_category_id="cat-2")

        response = self.client.get(self.url(), follow=True)

        self.assertRedirects(response, reverse("admin:home_session_changelist"))
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("Other" in m for m in messages))


class DiscordTeardownViewTests(DiscordViewsTestCase):
    def url(self):
        return reverse("admin:session_discord_teardown", args=[self.session.id])

    def test_get_renders_confirmation_with_warning(self):
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/discord_teardown.html")
        self.assertContains(response, "hard to undo")

    def test_get_without_category_shows_error_instead_of_form(self):
        session = SessionFactory.create(title="No Discord")
        url = reverse("admin:session_discord_teardown", args=[session.id])

        response = self.client.get(url)

        self.assertContains(response, "no Discord category recorded")
        self.assertNotContains(response, "Are you sure")

    @rsps.activate
    def test_post_runs_teardown_and_emails_report(self):
        stub_discord_api(
            channels=[{"id": "chan-x", "name": "team-bee", "parent_id": "cat-1"}],
        )

        response = self.client.post(self.url())

        self.assertRedirects(response, reverse("admin:home_session_changelist"))
        self.assertEqual(len(mail.outbox), 1)
        email_message = mail.outbox[0]
        self.assertEqual(email_message.to, ["admin@example.com"])
        self.assertIn("Discord teardown complete", email_message.subject)
        # The archived channel is listed with its session-prefixed name.
        self.assertIn("session-4-team-bee", email_message.body)
        # Missing session/alumni roles were created and reported.
        self.assertIn("Stars", email_message.body)

    @rsps.activate
    def test_post_without_category_redirects_without_enqueueing(self):
        session = SessionFactory.create(title="No Discord")
        url = reverse("admin:session_discord_teardown", args=[session.id])

        response = self.client.post(url, follow=True)

        self.assertRedirects(response, reverse("admin:home_session_changelist"))
        self.assertEqual(len(rsps.calls), 0)
        self.assertEqual(mail.outbox, [])
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("no Discord category" in m for m in messages))

    @override_settings(
        ALLOWED_EMAILS_FOR_TESTING=["admin@example.com", "other-admin2@example.com"]
    )
    @rsps.activate
    def test_post_api_error_is_reported_in_email_and_ccs_superusers(self):
        other_admin = UserFactory.create(username="other-admin2", is_superuser=True)
        rsps.add(rsps.GET, f"{GUILD_URL}/roles", status=403)

        response = self.client.post(self.url())

        self.assertRedirects(response, reverse("admin:home_session_changelist"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Discord API error", mail.outbox[0].body)
        # Superusers are CCed on errors; the requester isn't CCed twice.
        self.assertEqual(mail.outbox[0].cc, [other_admin.email])

    def test_blocked_when_another_session_has_discord_active(self):
        SessionFactory.create(title="Other", discord_category_id="cat-2")

        response = self.client.get(self.url(), follow=True)

        self.assertRedirects(response, reverse("admin:home_session_changelist"))
        messages = [str(m) for m in response.context["messages"]]
        self.assertTrue(any("Other" in m for m in messages))

    def test_non_organizer_staff_gets_404(self):
        outsider = UserFactory.create(username="outsider2", is_staff=True)
        self.client.force_login(outsider)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 404)


class DiscordTeamMessagesViewTests(DiscordViewsTestCase):
    def url(self):
        return reverse("admin:session_discord_team_messages", args=[self.session.id])

    def test_renders_message_per_team(self):
        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "admin/discord_team_messages.html")
        self.assertContains(response, "#team-bee")
        self.assertContains(response, f"Project: {self.team.project.name}")
        # The member without a Discord username appears by name.
        self.assertContains(response, "Jane Doe")

    def test_non_organizer_staff_gets_404(self):
        outsider = UserFactory.create(username="outsider3", is_staff=True)
        self.client.force_login(outsider)

        response = self.client.get(self.url())

        self.assertEqual(response.status_code, 404)
