"""
Tests for the Discord session setup/teardown orchestration
(home.integrations.discord.session_service) against a stubbed Discord API
(see home.tests.discord.stubs) — the real DiscordClient runs over HTTP
intercepted by the responses library.

Full-flow tests drive ``DiscordSessionSetup.run()``/
``DiscordSessionTeardown.run()``. Step tests seed just the instance state a
step reads and call the step directly.
"""

import responses as rsps
from django.test import TestCase

from accounts.factories import UserFactory
from home import constants
from home.factories import (
    DiscordMemberFactory,
    OrganizerFactory,
    SessionFactory,
    SessionMembershipFactory,
    TeamFactory,
)
from home.integrations.discord.client import (
    CATEGORY_TYPE,
    MEMBER_OVERWRITE,
    ROLE_OVERWRITE,
    TEXT_CHANNEL_TYPE,
    VIEW_CHANNEL,
    VOICE_CHANNEL_TYPE,
)
from home.integrations.discord.session_service import (
    CAPNAV_CHANNEL_TOPIC,
    SESSION_STAFF_PERMISSIONS,
    THREAD_AUTO_ARCHIVE_MINUTES,
    TRUSTED_MEMBER_PERMISSIONS,
    DiscordSessionSetup,
    DiscordSessionTeardown,
    MemberResolution,
    build_team_messages,
)
from home.models import DiscordMember, DiscordRole
from home.tests.discord.stubs import (
    BOT_ROLE_ID,
    STANDING_GUILD_ROLES,
    channel_creations,
    channel_deletions,
    channel_updates,
    member,
    member_role_updates,
    role_creations,
    stub_discord_api,
)

# The casefolded name -> id map the service builds from STANDING_GUILD_ROLES,
# for seeding step tests directly.
ROLE_MAP = {role["name"].casefold(): role["id"] for role in STANDING_GUILD_ROLES}

VIEW = str(VIEW_CHANNEL)
TRUSTED = str(TRUSTED_MEMBER_PERMISSIONS)
STAFF = str(SESSION_STAFF_PERMISSIONS)


def resolution(member_id, role, username="", guild_role_ids=frozenset()):
    member = None
    if member_id is not None:
        member = DiscordMember(
            discord_id=member_id, username=username, role_ids=list(guild_role_ids)
        )
    return MemberResolution(
        display_name=username or "someone",
        member=member,
        role=role,
    )


def _link_discord_member(user, member_id, username, roles=()):
    member = DiscordMemberFactory.create(
        discord_id=member_id,
        username=username,
        role_ids=list(roles),
    )
    user.profile.discord_member = member
    user.profile.save(update_fields=["discord_member"])
    return member


class SetupRunTests(TestCase):
    """Full setup flow through DiscordSessionSetup.run()."""

    def setUp(self):
        self.session = SessionFactory.create(title="Session 4", short_name="Session 4")
        self.team = TeamFactory.create(
            session=self.session,
            name="Bee",
            google_drive_folder="https://drive.google.com/bee",
        )
        self.navigator = SessionMembershipFactory.create(
            session=self.session, team=self.team, role=constants.NAVIGATOR
        )
        self.djangonaut = SessionMembershipFactory.create(
            session=self.session, team=self.team, role=constants.DJANGONAUT
        )
        _link_discord_member(self.navigator.user, "100", "novauser1")
        _link_discord_member(self.djangonaut.user, "102", "novauser2")
        self.guild_members = [
            member("100", "novauser1"),
            member("102", "novauser2"),
        ]

    @rsps.activate
    def test_creates_category_channels_and_persists_ids(self):
        stub_discord_api(
            roles=STANDING_GUILD_ROLES + [{"id": "r-bee", "name": "Bee"}],
            guild_members=self.guild_members,
        )

        report = DiscordSessionSetup(self.session).run()

        created = channel_creations()
        self.assertEqual(
            set(created),
            {
                "Session 4",
                "team-bee",
                "team-bee-voice",
                "captains-and-navigators",
                "session-announcements",
            },
        )
        self.assertEqual(created["Session 4"]["type"], CATEGORY_TYPE)

        team_channel = created["team-bee"]
        self.assertEqual(team_channel["type"], TEXT_CHANNEL_TYPE)
        self.assertEqual(team_channel["parent_id"], "new-channel-1")
        self.assertIn(
            {"id": "guild-1", "type": ROLE_OVERWRITE, "allow": "0", "deny": VIEW},
            team_channel["permission_overwrites"],
        )
        # Team members get the trusted-member set (pin, threads, reactions,
        # ...); Session Organizers additionally get to manage others' content.
        self.assertIn(
            {"id": "r-bee", "type": ROLE_OVERWRITE, "allow": TRUSTED, "deny": "0"},
            team_channel["permission_overwrites"],
        )
        self.assertIn(
            {"id": "r-org", "type": ROLE_OVERWRITE, "allow": STAFF, "deny": "0"},
            team_channel["permission_overwrites"],
        )
        self.assertIn(
            {"id": BOT_ROLE_ID, "type": ROLE_OVERWRITE, "allow": VIEW, "deny": "0"},
            team_channel["permission_overwrites"],
        )
        self.assertEqual(
            team_channel["default_auto_archive_duration"], THREAD_AUTO_ARCHIVE_MINUTES
        )

        voice_channel = created["team-bee-voice"]
        self.assertEqual(voice_channel["type"], VOICE_CHANNEL_TYPE)
        self.assertEqual(voice_channel["parent_id"], "new-channel-1")
        self.assertEqual(
            voice_channel["permission_overwrites"],
            team_channel["permission_overwrites"],
        )
        # Voice channels don't support topic/thread-archive fields.
        self.assertNotIn("default_auto_archive_duration", voice_channel)
        self.assertNotIn("topic", voice_channel)

        capnav = created["captains-and-navigators"]
        self.assertEqual(capnav["topic"], CAPNAV_CHANNEL_TOPIC)
        self.assertEqual(
            capnav["default_auto_archive_duration"], THREAD_AUTO_ARCHIVE_MINUTES
        )
        trusted_capnav_roles = {
            o["id"] for o in capnav["permission_overwrites"] if o["allow"] == TRUSTED
        }
        staff_capnav_roles = {
            o["id"] for o in capnav["permission_overwrites"] if o["allow"] == STAFF
        }
        self.assertEqual(trusted_capnav_roles, {"r-cap", "r-nav", "r-adv"})
        self.assertEqual(staff_capnav_roles, {"r-adm", "r-org"})

        announce = created["session-announcements"]
        trusted_announce_roles = {
            o["id"] for o in announce["permission_overwrites"] if o["allow"] == TRUSTED
        }
        staff_announce_roles = {
            o["id"] for o in announce["permission_overwrites"] if o["allow"] == STAFF
        }
        self.assertEqual(trusted_announce_roles, {"r-dj", "r-cap", "r-nav", "r-adv"})
        self.assertEqual(staff_announce_roles, {"r-adm", "r-org"})

        self.session.refresh_from_db()
        self.team.refresh_from_db()
        self.assertEqual(self.session.discord_category_id, "new-channel-1")
        self.assertEqual(self.team.discord_channel_id, "new-channel-2")
        self.assertEqual(self.team.discord_voice_channel_id, "new-channel-3")
        self.assertEqual(self.session.discord_capnav_channel_id, "new-channel-4")
        self.assertEqual(self.session.discord_announcements_channel_id, "new-channel-5")
        self.assertEqual(len(report.channels_created), 5)
        self.assertEqual(report.errors, [])

    @rsps.activate
    def test_second_run_updates_instead_of_creating(self):
        self.session.discord_category_id = "cat-1"
        self.session.discord_capnav_channel_id = "chan-capnav"
        self.session.discord_announcements_channel_id = "chan-announce"
        self.session.save()
        self.team.discord_channel_id = "chan-bee"
        self.team.discord_voice_channel_id = "chan-bee-voice"
        self.team.save()
        stub_discord_api(
            roles=STANDING_GUILD_ROLES + [{"id": "r-bee", "name": "Bee"}],
            guild_members=self.guild_members,
        )

        report = DiscordSessionSetup(self.session).run()

        self.assertEqual(channel_creations(), {})
        self.assertEqual(
            set(channel_updates()),
            {"cat-1", "chan-bee", "chan-bee-voice", "chan-capnav", "chan-announce"},
        )
        self.assertEqual(report.channels_created, [])
        self.assertEqual(len(report.channels_updated), 5)

    @rsps.activate
    def test_mirrors_guild_roles_for_announcement_mentions(self):
        """The mirror runs last, so roles this run created are included."""
        stub_discord_api(guild_members=self.guild_members)

        report = DiscordSessionSetup(self.session).run()

        mirrored = set(DiscordRole.objects.values_list("name", flat=True))
        self.assertIn("Djangonauts", mirrored)
        self.assertIn("Bee", mirrored)
        self.assertEqual(report.roles_synced, len(mirrored))

    @rsps.activate
    def test_missing_standing_role_aborts_before_touching_discord(self):
        roles = [
            role for role in STANDING_GUILD_ROLES if role["name"] not in ("Admins",)
        ] + [{"id": "r-bee", "name": "Bee"}]
        stub_discord_api(roles=roles, guild_members=self.guild_members)

        report = DiscordSessionSetup(self.session).run()

        self.assertTrue(any("Admins" in error for error in report.errors))
        self.assertEqual(role_creations(), [])
        self.assertEqual(channel_creations(), {})
        self.assertEqual(member_role_updates(), {})
        self.assertEqual(report.channels_created, [])

    @rsps.activate
    def test_team_named_like_reserved_role_aborts(self):
        self.team.name = "Admins"
        self.team.save(update_fields=["name"])
        stub_discord_api(roles=STANDING_GUILD_ROLES, guild_members=self.guild_members)

        report = DiscordSessionSetup(self.session).run()

        self.assertTrue(any("Admins" in error for error in report.errors))
        # No team role adopted and no channels built.
        self.assertEqual(role_creations(), [])
        self.assertEqual(channel_creations(), {})
        self.assertEqual(member_role_updates(), {})

    @rsps.activate
    def test_failed_member_update_keeps_other_members(self):
        # Member 100's role update fails; member 102 must still be updated,
        # and the count reflects only the roles actually granted.
        stub_discord_api(
            roles=STANDING_GUILD_ROLES + [{"id": "r-bee", "name": "Bee"}],
            guild_members=self.guild_members,
            fail_update_members={"100"},
        )

        report = DiscordSessionSetup(self.session).run()

        self.assertEqual(
            member_role_updates()["102"], {"roles": sorted({"r-bee", "r-dj"})}
        )
        self.assertEqual(report.roles_assigned, 2)
        self.assertEqual(len(report.errors), 1)


class SetupCategoryStepTests(TestCase):
    """DiscordSessionSetup.setup_category in isolation."""

    def setUp(self):
        self.session = SessionFactory.create(title="Session 4", short_name="Session 4")

    @rsps.activate
    def test_creates_category_and_persists_id(self):
        stub_discord_api()
        setup = DiscordSessionSetup(self.session)

        setup.setup_category()

        self.session.refresh_from_db()
        self.assertEqual(self.session.discord_category_id, "new-channel-1")
        self.assertEqual(setup.report.category_id, "new-channel-1")
        self.assertEqual(setup.report.channels_created, ["Session 4"])

    @rsps.activate
    def test_reuses_persisted_category_id(self):
        self.session.discord_category_id = "cat-1"
        self.session.save()
        stub_discord_api()
        setup = DiscordSessionSetup(self.session)

        setup.setup_category()

        self.assertEqual(channel_creations(), {})
        self.assertEqual(channel_updates(), {"cat-1": {"name": "Session 4"}})
        self.assertEqual(setup.report.category_id, "cat-1")

    @rsps.activate
    def test_stale_category_id_falls_back_to_create(self):
        self.session.discord_category_id = "gone-1"
        self.session.save()
        stub_discord_api(fail_update_channels={"gone-1": 404})
        setup = DiscordSessionSetup(self.session)

        setup.setup_category()

        self.session.refresh_from_db()
        self.assertEqual(self.session.discord_category_id, "new-channel-1")
        self.assertEqual(setup.report.category_id, "new-channel-1")

    @rsps.activate
    def test_adopts_existing_category_with_matching_name(self):
        stub_discord_api(
            channels=[{"id": "cat-77", "name": "session 4", "type": CATEGORY_TYPE}]
        )
        setup = DiscordSessionSetup(self.session)

        setup.setup_category()

        self.assertEqual(channel_creations(), {})
        self.session.refresh_from_db()
        self.assertEqual(self.session.discord_category_id, "cat-77")
        self.assertEqual(setup.report.category_id, "cat-77")


class SetupTeamChannelStepTests(TestCase):
    """DiscordSessionSetup.ensure_team_roles / setup_team_channels in isolation."""

    def setUp(self):
        self.session = SessionFactory.create(title="Session 4")
        self.team = TeamFactory.create(session=self.session, name="Bee")

    @rsps.activate
    def test_ensure_team_roles_creates_missing_role(self):
        stub_discord_api()
        setup = DiscordSessionSetup(self.session)
        setup.role_map = dict(ROLE_MAP)

        setup.ensure_team_roles()

        self.assertEqual(role_creations(), ["Bee"])
        self.assertEqual(setup.team_role_ids, {self.team.pk: "new-role-1"})
        self.assertEqual(setup.report.roles_created, ["Bee"])

    @rsps.activate
    def test_ensure_team_roles_reuses_existing_role(self):
        stub_discord_api()
        setup = DiscordSessionSetup(self.session)
        setup.role_map = dict(ROLE_MAP, bee="r-bee")

        setup.ensure_team_roles()

        self.assertEqual(role_creations(), [])
        self.assertEqual(setup.team_role_ids, {self.team.pk: "r-bee"})

    @rsps.activate
    def test_channel_error_is_recorded_and_processing_continues(self):
        stub_discord_api(fail_create_channels={"team-bee"})
        setup = DiscordSessionSetup(self.session)
        setup.role_map = dict(ROLE_MAP, bee="r-bee")
        setup.team_role_ids = {self.team.pk: "r-bee"}
        setup.report.category_id = "cat-1"

        setup.setup_team_channels()

        self.assertTrue(any("Bee" in error for error in setup.report.errors))
        self.team.refresh_from_db()
        self.assertEqual(self.team.discord_channel_id, "")
        # The voice channel is still created despite the text channel failing.
        self.assertEqual(setup.report.channels_created, ["team-bee-voice"])
        self.assertEqual(self.team.discord_voice_channel_id, "new-channel-1")


class SetupSharedChannelsStepTests(TestCase):
    """DiscordSessionSetup.setup_shared_channels in isolation."""

    def setUp(self):
        self.session = SessionFactory.create(title="Session 4")

    @rsps.activate
    def test_capnav_channel_gets_topic_and_permission_split(self):
        stub_discord_api()
        setup = DiscordSessionSetup(self.session)
        setup.role_map = dict(ROLE_MAP)
        setup.report.category_id = "cat-1"

        setup.setup_shared_channels()

        capnav = channel_creations()["captains-and-navigators"]
        self.assertEqual(capnav["topic"], CAPNAV_CHANNEL_TOPIC)
        self.assertEqual(
            capnav["default_auto_archive_duration"], THREAD_AUTO_ARCHIVE_MINUTES
        )
        trusted_roles = {
            o["id"] for o in capnav["permission_overwrites"] if o["allow"] == TRUSTED
        }
        staff_roles = {
            o["id"] for o in capnav["permission_overwrites"] if o["allow"] == STAFF
        }
        self.assertEqual(trusted_roles, {"r-cap", "r-nav", "r-adv"})
        self.assertEqual(staff_roles, {"r-adm", "r-org"})


class SetupMemberRoleStepTests(TestCase):
    """DiscordSessionSetup.resolve_members / assign_member_roles in isolation."""

    def setUp(self):
        self.session = SessionFactory.create(title="Session 4")
        self.team = TeamFactory.create(session=self.session, name="Bee")
        self.navigator = SessionMembershipFactory.create(
            session=self.session, team=self.team, role=constants.NAVIGATOR
        )
        self.djangonaut = SessionMembershipFactory.create(
            session=self.session, team=self.team, role=constants.DJANGONAUT
        )
        _link_discord_member(self.navigator.user, "100", "novauser1")
        _link_discord_member(self.djangonaut.user, "102", "novauser2")
        self.guild_members = [
            member("100", "novauser1"),
            member("102", "novauser2"),
        ]

    def build_setup(self):
        setup = DiscordSessionSetup(self.session)
        setup.role_map = dict(ROLE_MAP, bee="r-bee")
        setup.team_role_ids = {self.team.pk: "r-bee"}
        return setup

    @rsps.activate
    def test_assigns_team_and_membership_roles_to_resolved_members(self):
        stub_discord_api(guild_members=self.guild_members)
        setup = self.build_setup()

        setup.resolve_members()
        setup.assign_member_roles()

        self.assertEqual(
            member_role_updates(),
            {
                "100": {"roles": sorted({"r-bee", "r-nav"})},
                "102": {"roles": sorted({"r-bee", "r-dj"})},
            },
        )
        self.assertEqual(setup.report.roles_assigned, 4)
        self.assertEqual(setup.report.unresolved, [])

    @rsps.activate
    def test_existing_roles_are_kept_and_not_counted(self):
        # The navigator already holds an unrelated role and their program
        # role; the PATCH must keep both and only count the team role.
        nav_member = self.navigator.user.profile.discord_member
        nav_member.role_ids = ["r-other", "r-nav"]
        nav_member.save(update_fields=["role_ids"])
        stub_discord_api(guild_members=self.guild_members)
        setup = self.build_setup()

        setup.resolve_members()
        setup.assign_member_roles()

        self.assertEqual(
            member_role_updates()["100"],
            {"roles": sorted({"r-other", "r-nav", "r-bee"})},
        )
        self.assertEqual(setup.report.roles_assigned, 3)

    @rsps.activate
    def test_members_holding_all_roles_are_skipped(self):
        nav_member = self.navigator.user.profile.discord_member
        nav_member.role_ids = ["r-bee", "r-nav"]
        nav_member.save(update_fields=["role_ids"])
        dj_member = self.djangonaut.user.profile.discord_member
        dj_member.role_ids = ["r-bee", "r-dj"]
        dj_member.save(update_fields=["role_ids"])
        stub_discord_api(guild_members=self.guild_members)
        setup = self.build_setup()

        setup.resolve_members()
        setup.assign_member_roles()

        self.assertEqual(member_role_updates(), {})
        self.assertEqual(setup.report.roles_assigned, 0)

    @rsps.activate
    def test_unresolved_members_are_reported_and_skipped(self):
        SessionMembershipFactory.create(
            session=self.session, team=self.team, role=constants.CAPTAIN
        )
        SessionMembershipFactory.create(
            session=self.session,
            team=self.team,
            role=constants.CAPTAIN,
            user=UserFactory.create(username="ghost"),
        )
        # No DiscordMember links — stay unresolved.
        stub_discord_api(guild_members=self.guild_members)
        setup = self.build_setup()

        setup.resolve_members()
        setup.assign_member_roles()

        self.assertEqual(len(setup.report.unresolved), 2)
        self.assertEqual({r.member_id for r in setup.report.unresolved}, {None})
        self.assertEqual(set(member_role_updates()), {"100", "102"})


class BuildTeamMessagesTests(TestCase):
    """build_team_messages composes text from the database alone.

    With the responses mock active and no endpoints registered, any API
    call would fail the test.
    """

    @rsps.activate
    def test_team_message_content(self):
        session = SessionFactory.create(title="Session 4")
        team = TeamFactory.create(
            session=session,
            name="Bee",
            google_drive_folder="https://drive.google.com/bee",
        )
        navigator = SessionMembershipFactory.create(
            session=session, team=team, role=constants.NAVIGATOR
        )
        # No Discord username: the captain falls back to their full name.
        SessionMembershipFactory.create(
            session=session, team=team, role=constants.CAPTAIN
        )
        djangonaut = SessionMembershipFactory.create(
            session=session, team=team, role=constants.DJANGONAUT
        )
        _link_discord_member(navigator.user, "100", "novauser1")
        _link_discord_member(djangonaut.user, "102", "novauser2")

        messages = build_team_messages(session)

        self.assertEqual(len(rsps.calls), 0)
        self.assertEqual(len(messages), 1)
        message = messages[0]
        self.assertEqual(message.team_name, "Bee")
        self.assertEqual(message.channel_name, "team-bee")
        expected_url = f"https://example.com{team.get_absolute_url()}"
        self.assertEqual(
            message.content,
            f"Project: {team.project.name}\n"
            "Navigator: @novauser1\n"
            "Captain: Jane Doe\n"
            "Djangonauts: @novauser2\n"
            f"Team page: {expected_url}\n"
            "Team Drive folder: https://drive.google.com/bee",
        )

    @rsps.activate
    def test_team_without_members_or_drive_folder(self):
        session = SessionFactory.create(title="Session 4")
        team = TeamFactory.create(session=session, name="Bee", google_drive_folder="")

        messages = build_team_messages(session)

        self.assertEqual(
            messages[0].content,
            f"Project: {team.project.name}\n"
            "Navigator: (none)\n"
            "Captain: (none)\n"
            "Djangonauts: (none)\n"
            f"Team page: https://example.com{team.get_absolute_url()}\n"
            "Team Drive folder: (not set)",
        )


class TeardownFixtureMixin:
    """Session/team/member fixtures shared by the teardown test classes."""

    def setUp(self):
        self.session = SessionFactory.create(
            title="Session 4",
            short_name="Session 4",
            discord_category_id="cat-1",
            discord_capnav_channel_id="chan-capnav",
            discord_announcements_channel_id="chan-announce",
        )
        self.team = TeamFactory.create(
            session=self.session,
            name="Bee",
            discord_channel_id="chan-bee",
            discord_voice_channel_id="chan-bee-voice",
        )
        self.navigator = SessionMembershipFactory.create(
            session=self.session, team=self.team, role=constants.NAVIGATOR
        )
        self.djangonaut = SessionMembershipFactory.create(
            session=self.session, team=self.team, role=constants.DJANGONAUT
        )
        self.organizer = OrganizerFactory.create(
            session=self.session, with_permissions=False
        )
        self.guild_members = [
            member("100", "novauser1", roles=["r-nav", "r-bee"]),
            member("102", "novauser2", roles=["r-dj", "r-bee"]),
            member("103", "orga", roles=["r-org"]),
            member("200", "admin-ann", roles=["r-adm"]),
            member("201", "advisor-avi", roles=["r-adv"]),
            # A leftover captain from an earlier session, not in this one.
            member("202", "old-captain", roles=["r-cap"]),
            member("203", "bystander", roles=[]),
        ]
        self.channels = [
            {"id": "chan-bee", "name": "team-bee", "parent_id": "cat-1"},
            {"id": "chan-bee-voice", "name": "team-bee-voice", "parent_id": "cat-1"},
            {
                "id": "chan-capnav",
                "name": "captains-and-navigators",
                "parent_id": "cat-1",
            },
            {
                "id": "chan-announce",
                "name": "session-announcements",
                "parent_id": "cat-1",
            },
            {"id": "chan-organizing", "name": "organizing", "parent_id": "cat-1"},
            {"id": "chan-other", "name": "general", "parent_id": "other-cat"},
        ]
        self.roles = STANDING_GUILD_ROLES + [
            {"id": "r-bee", "name": "Bee"},
            {"id": "r-past-nav", "name": "Past Navigators"},
            {"id": "r-past-cap", "name": "Past Captains"},
            {"id": "r-past-org", "name": "Past Session Organizers"},
            {"id": "r-stars", "name": "Stars"},
        ]

    def seeded_resolutions(self):
        return {
            self.navigator.pk: resolution("100", constants.NAVIGATOR, "novauser1"),
            self.djangonaut.pk: resolution("102", constants.DJANGONAUT, "novauser2"),
            self.organizer.pk: resolution("103", constants.ORGANIZER, "orga"),
        }


class TeardownRunTests(TeardownFixtureMixin, TestCase):
    """Full teardown flow through DiscordSessionTeardown.run()."""

    def setUp(self):
        super().setUp()
        _link_discord_member(self.navigator.user, "100", "novauser1")
        _link_discord_member(self.djangonaut.user, "102", "novauser2")
        _link_discord_member(self.organizer.user, "103", "orga")

    def stub_api(self, **overrides):
        kwargs = dict(
            roles=self.roles,
            channels=self.channels,
            guild_members=self.guild_members,
        )
        kwargs.update(overrides)
        stub_discord_api(**kwargs)

    @rsps.activate
    def test_requires_category_id(self):
        self.session.discord_category_id = ""
        with self.assertRaises(ValueError):
            DiscordSessionTeardown(self.session).run()
        self.assertEqual(len(rsps.calls), 0)

    @rsps.activate
    def test_channels_get_direct_member_access_without_role_overwrites(self):
        self.stub_api()

        report = DiscordSessionTeardown(self.session).run()

        updates = channel_updates()
        # Channels outside the category are untouched.
        self.assertNotIn("chan-other", updates)
        # Voice channels are deleted, not archived.
        self.assertNotIn("chan-bee-voice", updates)

        def allowed_members(channel_id):
            return {
                o["id"]
                for o in updates[channel_id]["permission_overwrites"]
                if o["type"] == MEMBER_OVERWRITE
            }

        # Team channel: team members + organizers.
        self.assertEqual(allowed_members("chan-bee"), {"100", "102", "103"})
        # Capnav: navigators + captains + organizers (no captains this session).
        self.assertEqual(allowed_members("chan-capnav"), {"100", "103"})
        # Announcements: every session member keeps access + Admins/Advisors.
        self.assertEqual(
            allowed_members("chan-announce"), {"100", "102", "103", "200", "201"}
        )
        # Everything else: organizers + Admins/Advisors holders.
        self.assertEqual(allowed_members("chan-organizing"), {"103", "200", "201"})

        for channel_id in ("chan-bee", "chan-capnav", "chan-announce"):
            role_overwrites = [
                o
                for o in updates[channel_id]["permission_overwrites"]
                if o["type"] == ROLE_OVERWRITE
            ]
            self.assertEqual(
                role_overwrites,
                [
                    {
                        "id": "guild-1",
                        "type": ROLE_OVERWRITE,
                        "allow": "0",
                        "deny": VIEW,
                    },
                    {
                        "id": BOT_ROLE_ID,
                        "type": ROLE_OVERWRITE,
                        "allow": VIEW,
                        "deny": "0",
                    },
                ],
            )
        # Archived channels are renamed with the session prefix.
        self.assertEqual(updates["chan-bee"]["name"], "session-4-team-bee")
        self.assertEqual(
            updates["chan-capnav"]["name"], "session-4-captains-and-navigators"
        )
        self.assertEqual(
            report.channels_processed,
            [
                "session-4-team-bee",
                "session-4-captains-and-navigators",
                "session-4-session-announcements",
                "session-4-organizing",
            ],
        )

    @rsps.activate
    def test_voice_channels_are_deleted(self):
        self.stub_api()

        report = DiscordSessionTeardown(self.session).run()

        self.assertEqual(channel_deletions(), ["chan-bee-voice"])
        self.assertEqual(report.channels_deleted, ["team-bee-voice"])
        self.team.refresh_from_db()
        self.assertEqual(self.team.discord_voice_channel_id, "")

    @rsps.activate
    def test_member_role_math(self):
        self.stub_api()

        report = DiscordSessionTeardown(self.session).run()

        updates = {
            user_id: set(payload["roles"])
            for user_id, payload in member_role_updates().items()
        }
        session_role_id = "new-role-1"  # "Session 4" role created during teardown
        self.assertEqual(updates["100"], {"r-bee", "r-past-nav", session_role_id})
        self.assertEqual(updates["102"], {"r-bee", "r-stars", session_role_id})
        self.assertEqual(updates["103"], {"r-past-org", session_role_id})
        # Non-session holder of an active role is stripped too.
        self.assertEqual(updates["202"], set())
        # Members with nothing to change are not touched.
        self.assertNotIn("200", updates)
        self.assertNotIn("203", updates)

        self.assertEqual(report.members_updated, 4)
        self.assertEqual(
            report.roles_stripped,
            {
                "Djangonauts": 1,
                "Captains": 1,
                "Navigators": 1,
                "Session Organizers": 1,
            },
        )

    @rsps.activate
    def test_creates_missing_session_and_alumni_roles(self):
        self.stub_api(roles=STANDING_GUILD_ROLES + [{"id": "r-bee", "name": "Bee"}])

        report = DiscordSessionTeardown(self.session).run()

        self.assertEqual(
            set(report.roles_created),
            {
                "Session 4",
                "Past Navigators",
                "Past Captains",
                "Past Session Organizers",
                "Stars",
            },
        )

    @rsps.activate
    def test_unresolved_members_reported(self):
        SessionMembershipFactory.create(
            session=self.session, team=self.team, role=constants.CAPTAIN
        )
        self.stub_api()

        report = DiscordSessionTeardown(self.session).run()

        self.assertEqual(len(report.unresolved), 1)
        self.assertEqual(report.unresolved[0].role, constants.CAPTAIN)

    @rsps.activate
    def test_announcements_channel_retains_all_session_members(self):
        self.stub_api()

        DiscordSessionTeardown(self.session).run()

        announce = channel_updates()["chan-announce"]
        retained = {
            o["id"]
            for o in announce["permission_overwrites"]
            if o["type"] == MEMBER_OVERWRITE
        }
        # Navigator (100), Djangonaut (102), Organizer (103) + Admin/Advisor.
        self.assertEqual(retained, {"100", "102", "103", "200", "201"})


class TeardownArchiveStepTests(TeardownFixtureMixin, TestCase):
    """DiscordSessionTeardown.archive_channels with seeded resolutions.

    Seeding ``resolutions``/``guild_members`` directly means no member-search
    stubbing is needed to exercise the channel archival logic.
    """

    def build_teardown(self):
        teardown = DiscordSessionTeardown(self.session)
        teardown.role_map = {role["name"].casefold(): role["id"] for role in self.roles}
        teardown.resolutions = self.seeded_resolutions()
        teardown.guild_members = self.guild_members
        return teardown

    def test_archived_channel_name_prefixes_with_session(self):
        teardown = DiscordSessionTeardown(self.session)

        self.assertEqual(
            teardown.archived_channel_name("team-pluto"), "session-4-team-pluto"
        )
        # Already-prefixed names pass through, so reruns don't stack prefixes.
        self.assertEqual(
            teardown.archived_channel_name("session-4-team-pluto"),
            "session-4-team-pluto",
        )

    @rsps.activate
    def test_archive_error_recorded_and_processing_continues(self):
        stub_discord_api(channels=self.channels, fail_update_channels={"chan-bee": 403})
        teardown = self.build_teardown()

        teardown.archive_channels()

        self.assertTrue(any("team-bee" in error for error in teardown.report.errors))
        self.assertEqual(len(teardown.report.channels_processed), 3)
        # The voice channel is still deleted despite the archive failure.
        self.assertEqual(teardown.report.channels_deleted, ["team-bee-voice"])

    @rsps.activate
    def test_voice_channel_delete_error_recorded_and_processing_continues(self):
        stub_discord_api(
            channels=self.channels, fail_delete_channels={"chan-bee-voice"}
        )
        teardown = self.build_teardown()

        teardown.archive_channels()

        self.assertTrue(
            any("team-bee-voice" in error for error in teardown.report.errors)
        )
        self.team.refresh_from_db()
        self.assertEqual(self.team.discord_voice_channel_id, "chan-bee-voice")
        # The remaining channels are still archived.
        self.assertEqual(len(teardown.report.channels_processed), 4)
