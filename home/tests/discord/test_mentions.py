"""
Tests for rewriting ``@Role`` names into Discord role pings
(home.integrations.discord.service.resolve_role_mentions).

The interesting cases are all about what must *not* be rewritten: announcement
copy is full of ``@``s that aren't roles, and a false positive posts an
unreadable id or pings the wrong people.
"""

from django.test import TestCase

from accounts.factories import DiscordRoleFactory
from home.integrations.discord.service import resolve_role_mentions


class ResolveRoleMentionsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.djangonauts = DiscordRoleFactory(name="Djangonauts", discord_id="1")
        cls.navigators = DiscordRoleFactory(name="Navigators", discord_id="2")
        cls.organizers = DiscordRoleFactory(name="Session Organizers", discord_id="3")

    def test_rewrites_known_role(self):
        content, roles = resolve_role_mentions("Hello @Djangonauts, welcome!")

        self.assertEqual(content, "Hello <@&1>, welcome!")
        self.assertEqual(roles, [self.djangonauts])

    def test_matches_case_insensitively(self):
        """Role names are maintained by humans, so casing must not matter."""
        content, roles = resolve_role_mentions("Hi @djangonauts")

        self.assertEqual(content, "Hi <@&1>")
        self.assertEqual(roles, [self.djangonauts])

    def test_prefers_the_longest_matching_name(self):
        """A multi-word role must not lose its tail to a shorter prefix match."""
        DiscordRoleFactory(name="Session", discord_id="4")

        content, roles = resolve_role_mentions("Ask @Session Organizers for help")

        self.assertEqual(content, "Ask <@&3> for help")
        self.assertEqual(roles, [self.organizers])

    def test_lists_each_role_once_in_order(self):
        content, roles = resolve_role_mentions(
            "@Navigators and @Djangonauts, @Navigators again"
        )

        self.assertEqual(content, "<@&2> and <@&1>, <@&2> again")
        self.assertEqual(roles, [self.navigators, self.djangonauts])

    def test_leaves_unknown_mentions_alone(self):
        content, roles = resolve_role_mentions("Ping @Captains about it")

        self.assertEqual(content, "Ping @Captains about it")
        self.assertEqual(roles, [])

    def test_leaves_email_addresses_alone(self):
        """The CoC address ends every welcome message and must survive intact."""
        DiscordRoleFactory(name="Djangonaut", discord_id="5")

        content, roles = resolve_role_mentions("Report issues to CoC@djangonaut.space")

        self.assertEqual(content, "Report issues to CoC@djangonaut.space")
        self.assertEqual(roles, [])

    def test_does_not_match_a_longer_word(self):
        content, roles = resolve_role_mentions("@Djangonautsville is not a role")

        self.assertEqual(content, "@Djangonautsville is not a role")
        self.assertEqual(roles, [])

    def test_no_roles_mirrored_leaves_content_unchanged(self):
        """Before the first sync there is nothing to resolve against."""
        self.djangonauts.delete()
        self.navigators.delete()
        self.organizers.delete()

        content, roles = resolve_role_mentions("Hello @Djangonauts")

        self.assertEqual(content, "Hello @Djangonauts")
        self.assertEqual(roles, [])
