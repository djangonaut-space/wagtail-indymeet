"""
Discord channel and role orchestration for session setup and teardown.

``DiscordSessionSetup`` builds a category with per-team text and voice
channels plus the shared captains-and-navigators and session-announcements
channels, and wires access through Discord roles.
``DiscordSessionTeardown`` archives the category: team voice channels are
deleted, every remaining channel's role-based access is replaced with direct
member access (so session roles can be reused), participants get the session
and past-*/stars roles, and the active program roles are stripped guild-wide.
``build_team_messages`` composes the copy/paste welcome message per team from
the database alone, so the admin view can regenerate it at any time.

Each action runs as a sequence of small steps — see the ``run()`` methods,
which are the entry points the background tasks in
``home.tasks.discord_session`` call — with shared state (guild role map,
member resolutions, report) on the instance, so tests can seed state and
exercise a single step.

Event sync lives in ``home.integrations.discord.service``; this module only
depends on its client singleton and enabled check.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field

import requests
from django.conf import settings
from django.utils.text import slugify

from home import constants
from home.integrations.discord.client import (
    ADD_REACTIONS,
    ATTACH_FILES,
    CATEGORY_TYPE,
    CREATE_PRIVATE_THREADS,
    CREATE_PUBLIC_THREADS,
    EMBED_LINKS,
    MANAGE_MESSAGES,
    MANAGE_THREADS,
    MEMBER_OVERWRITE,
    PIN_MESSAGES,
    READ_MESSAGE_HISTORY,
    ROLE_OVERWRITE,
    SEND_MESSAGES,
    SEND_MESSAGES_IN_THREADS,
    SEND_POLLS,
    SEND_VOICE_MESSAGES,
    TEXT_CHANNEL_TYPE,
    USE_EXTERNAL_EMOJIS,
    USE_EXTERNAL_STICKERS,
    VIEW_CHANNEL,
    VOICE_CHANNEL_TYPE,
)
from home.integrations.discord.service import discord_client

logger = logging.getLogger(__name__)

# Names of the standing roles on the Djangonaut Space Discord server. Role
# lookup is case-insensitive, but the roles themselves must already exist —
# setup aborts and reports missing standing roles rather than creating them,
# so a typo here or on the server can't silently split access across
# duplicate roles.
DJANGONAUTS_ROLE = "Djangonauts"
CAPTAINS_ROLE = "Captains"
NAVIGATORS_ROLE = "Navigators"
SESSION_ORGANIZERS_ROLE = "Session Organizers"
ADMINS_ROLE = "Admins"
ADVISORS_ROLE = "Advisors"
PAST_NAVIGATORS_ROLE = "Past Navigators"
PAST_CAPTAINS_ROLE = "Past Captains"
PAST_ORGANIZERS_ROLE = "Past Session Organizers"
STARS_ROLE = "Stars"

STANDING_ROLES = (
    DJANGONAUTS_ROLE,
    CAPTAINS_ROLE,
    NAVIGATORS_ROLE,
    SESSION_ORGANIZERS_ROLE,
    ADMINS_ROLE,
    ADVISORS_ROLE,
)

# Membership role -> standing Discord role granted at setup.
MEMBERSHIP_DISCORD_ROLES = {
    constants.DJANGONAUT: DJANGONAUTS_ROLE,
    constants.CAPTAIN: CAPTAINS_ROLE,
    constants.NAVIGATOR: NAVIGATORS_ROLE,
    constants.ORGANIZER: SESSION_ORGANIZERS_ROLE,
}

# Membership role -> alumni Discord role granted at teardown.
PAST_DISCORD_ROLES = {
    constants.DJANGONAUT: STARS_ROLE,
    constants.CAPTAIN: PAST_CAPTAINS_ROLE,
    constants.NAVIGATOR: PAST_NAVIGATORS_ROLE,
    constants.ORGANIZER: PAST_ORGANIZERS_ROLE,
}

CAPNAV_CHANNEL_NAME = "captains-and-navigators"
ANNOUNCEMENTS_CHANNEL_NAME = "session-announcements"

CAPNAV_CHANNEL_TOPIC = (
    "This channel is a place for navigators and captains to ask each other "
    "questions, share tips and ask for advice on being a mentor in "
    "Djangonaut Space. This will be archived after the session.\n\n"
    "Please refrain from mentioning Djangonaut's names when speaking critically."
)

# Explicit "above average" grant for everyone with view access to a session
# channel, rather than relying on whatever the guild's default @everyone
# permissions happen to be. Excludes MANAGE_MESSAGES/MANAGE_THREADS: members
# can pin their own conversation and manage their own threads, but can't
# delete another member's message or take over a thread they didn't start.
TRUSTED_MEMBER_PERMISSIONS = (
    VIEW_CHANNEL
    | SEND_MESSAGES
    | EMBED_LINKS
    | ATTACH_FILES
    | ADD_REACTIONS
    | USE_EXTERNAL_EMOJIS
    | USE_EXTERNAL_STICKERS
    | READ_MESSAGE_HISTORY
    | CREATE_PUBLIC_THREADS
    | CREATE_PRIVATE_THREADS
    | SEND_MESSAGES_IN_THREADS
    | PIN_MESSAGES
    | SEND_VOICE_MESSAGES
    | SEND_POLLS
)

# Session Organizers and Admins additionally get to delete other members'
# messages and manage (archive/delete/lock) threads they didn't start.
SESSION_STAFF_PERMISSIONS = (
    TRUSTED_MEMBER_PERMISSIONS | MANAGE_MESSAGES | MANAGE_THREADS
)

# Threads in session channels stay active for a week of inactivity instead of
# Discord's 3-day default.
THREAD_AUTO_ARCHIVE_MINUTES = 7 * 24 * 60

# Role names that a per-team role must never collide with: adopting one of
# these as a "team role" would gate the team channel on a privileged/standing
# role (or a to-be-created alumni role) and leak access. Setup refuses to run
# when a team is named like one of these rather than silently reusing it.
RESERVED_ROLE_NAMES = frozenset(
    name.casefold() for name in (*STANDING_ROLES, *PAST_DISCORD_ROLES.values())
)

GUILD_MEMBER_PAGE_SIZE = 1000


@dataclass
class MemberResolution:
    """Maps a session membership to a Discord guild member."""

    display_name: str
    discord_username: str
    member_id: str | None
    role: str
    guild_role_ids: frozenset[str] = frozenset()


@dataclass
class TeamMessage:
    team_name: str
    channel_name: str
    content: str


@dataclass
class SetupReport:
    category_id: str = ""
    channels_created: list[str] = field(default_factory=list)
    channels_updated: list[str] = field(default_factory=list)
    roles_created: list[str] = field(default_factory=list)
    roles_assigned: int = 0
    announcements_created: int = 0
    unresolved: list[MemberResolution] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class TeardownReport:
    channels_processed: list[str] = field(default_factory=list)
    channels_deleted: list[str] = field(default_factory=list)
    roles_created: list[str] = field(default_factory=list)
    members_updated: int = 0
    roles_stripped: dict[str, int] = field(default_factory=dict)
    unresolved: list[MemberResolution] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def _guild_role_map() -> dict[str, str]:
    """Return a casefolded role-name -> role-id map for the guild.

    Casefolded because guild role names are maintained by humans and the
    exact capitalization ("Navigators" vs "navigators") must not matter.
    """
    roles = discord_client.get_guild_roles(guild_id=settings.DISCORD_GUILD_ID)
    return {role["name"].casefold(): role["id"] for role in roles}


def _ensure_role(name: str, role_map: dict[str, str], roles_created: list[str]) -> str:
    """Return the role id for ``name``, creating the role when absent."""
    key = name.casefold()
    if key not in role_map:
        role = discord_client.create_guild_role(
            guild_id=settings.DISCORD_GUILD_ID, name=name
        )
        role_map[key] = role["id"]
        roles_created.append(name)
    return role_map[key]


def _resolve_members(memberships) -> dict[int, MemberResolution]:
    """Resolve memberships to guild members, keyed by membership pk.

    One search per distinct configured username; a resolution with
    ``member_id=None`` means the username was blank or had no exact
    (case-insensitive) match in the guild, and needs manual follow-up.
    """
    memberships = list(memberships)
    guild_members: dict[str, dict | None] = {}
    for membership in memberships:
        username = membership.user.profile.discord_username.strip()
        if not username or username.casefold() in guild_members:
            continue
        matches = discord_client.search_guild_members(
            guild_id=settings.DISCORD_GUILD_ID, query=username
        )
        guild_members[username.casefold()] = next(
            (
                match
                for match in matches
                if match["user"]["username"].casefold() == username.casefold()
            ),
            None,
        )

    resolutions = {}
    for membership in memberships:
        username = membership.user.profile.discord_username.strip()
        guild_member = guild_members.get(username.casefold()) if username else None
        resolutions[membership.pk] = MemberResolution(
            display_name=membership.user.get_full_name() or membership.user.username,
            discord_username=username,
            member_id=guild_member["user"]["id"] if guild_member else None,
            role=membership.role,
            guild_role_ids=(
                frozenset(guild_member["roles"]) if guild_member else frozenset()
            ),
        )
    return resolutions


def _role_permission_overwrite(role_id: str, allow: int = VIEW_CHANNEL) -> dict:
    """Let members holding this role see an otherwise-hidden channel.

    Session channels pair one ``_everyone_deny_permission_overwrite()`` entry
    with allows like this one, so visibility is controlled entirely by role
    membership.
    """
    return {
        "id": role_id,
        "type": ROLE_OVERWRITE,
        "allow": str(allow),
        "deny": "0",
    }


def _member_permission_overwrite(member_id: str) -> dict:
    """Let one specific guild member see an otherwise-hidden channel.

    Teardown swaps every channel's role permission overwrites for these
    per-member entries: the people keep access to their archived channels
    while the program roles (Djangonauts, Captains, ...) are stripped and
    freed up for the next session.
    """
    return {
        "id": member_id,
        "type": MEMBER_OVERWRITE,
        "allow": str(VIEW_CHANNEL),
        "deny": "0",
    }


def _grant_permissions_to_roles(
    role_map: dict[str, str], allow: int, *names: str
) -> list[dict]:
    """Permission overwrites granting ``allow`` to each of the named roles."""
    return [
        _role_permission_overwrite(role_map[name.casefold()], allow) for name in names
    ]


def _everyone_deny_permission_overwrite() -> dict:
    """Hide the channel from everyone not explicitly allowed.

    Discord channels are visible to the whole server by default; this deny
    on the @everyone role is what makes a session channel private, and every
    channel this module manages carries it. The @everyone role shares the
    guild's id, per Discord's data model.
    """
    return {
        "id": settings.DISCORD_GUILD_ID,
        "type": ROLE_OVERWRITE,
        "allow": "0",
        "deny": str(VIEW_CHANNEL),
    }


def _bot_role_permission_overwrite() -> dict:
    """Let the bot's own server role see every channel it manages.

    Discord only bypasses per-channel overwrites for Administrator — a
    guild-wide permission like Manage Channels is not enough. Without this
    entry, a channel that denies @everyone and grants only program/team
    roles becomes invisible to the bot itself the moment it's created.
    """
    return _role_permission_overwrite(settings.DISCORD_BOT_ROLE_ID)


def _list_all_guild_members() -> list[dict]:
    """Fetch the full guild member list (paginated; needs GUILD_MEMBERS intent)."""
    members: list[dict] = []
    after = None
    while True:
        page = discord_client.list_guild_members(
            guild_id=settings.DISCORD_GUILD_ID,
            limit=GUILD_MEMBER_PAGE_SIZE,
            after=after,
        )
        members.extend(page)
        if len(page) < GUILD_MEMBER_PAGE_SIZE:
            return members
        after = page[-1]["user"]["id"]


def team_channel_name(team) -> str:
    """Discord channel name for a team.

    Discord normalizes text-channel names to lowercase kebab-case; slugifying
    up front keeps our name stable across create/update comparisons.
    """
    return f"team-{slugify(team.name)}"


def team_voice_channel_name(team) -> str:
    """Discord voice channel name for a team, alongside its text channel."""
    return f"{team_channel_name(team)}-voice"


def _membership_mention(membership) -> str:
    """Copy/paste text for one person: ``@username``, or their name without one."""
    username = membership.user.profile.discord_username.strip()
    if username:
        return f"@{username}"
    return membership.user.get_full_name() or membership.user.username


def build_team_messages(session) -> list[TeamMessage]:
    """Compose the copy/paste welcome message for each team channel.

    Built entirely from the database — no Discord API calls — so organizers
    can regenerate the messages at any time, independent of the setup run.
    Team page and Drive folder are labeled bare URLs because organizers send
    these as regular users, and Discord doesn't render masked links for them.
    """
    mentions_by_team: defaultdict[int, defaultdict[str, list[str]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for membership in session.session_memberships.accepted().select_related(
        "user__profile"
    ):
        if membership.team_id:
            mentions_by_team[membership.team_id][membership.role].append(
                _membership_mention(membership)
            )

    messages = []
    for team in session.teams.select_related("project"):
        team_mentions = mentions_by_team[team.pk]

        def mentions(role: str) -> str:
            return ", ".join(team_mentions[role]) or "(none)"

        drive_folder = team.google_drive_folder or "(not set)"
        messages.append(
            TeamMessage(
                team_name=team.name,
                channel_name=team_channel_name(team),
                content=(
                    f"Project: {team.project.name}\n"
                    f"Navigator: {mentions(constants.NAVIGATOR)}\n"
                    f"Captain: {mentions(constants.CAPTAIN)}\n"
                    f"Djangonauts: {mentions(constants.DJANGONAUT)}\n"
                    f"Team page: {settings.BASE_URL}{team.get_absolute_url()}\n"
                    f"Team Drive folder: {drive_folder}"
                ),
            )
        )
    return messages


class _DiscordSessionAction:
    """State and steps shared by the setup and teardown orchestrations."""

    report: SetupReport | TeardownReport

    def __init__(self, session) -> None:
        self.session = session
        self.teams = list(session.teams.select_related("project"))
        self.memberships = list(
            session.session_memberships.accepted().select_related(
                "user__profile", "team"
            )
        )
        self.role_map: dict[str, str] = {}
        self.resolutions: dict[int, MemberResolution] = {}

    def load_role_map(self) -> None:
        self.role_map = _guild_role_map()

    def report_missing_bot_role(self) -> bool:
        """Report a missing/misconfigured bot role id; truthy aborts the run.

        Every channel overwrite this module writes grants the bot's own role
        view access (see ``_bot_role_permission_overwrite``) — without a
        valid id here, that grant would target a nonexistent or wrong role,
        so it's checked up front rather than surfacing as 403s mid-run.
        """
        bot_role_id = settings.DISCORD_BOT_ROLE_ID
        if bot_role_id and bot_role_id in self.role_map.values():
            return False
        self.report.errors.append(
            "DISCORD_BOT_ROLE_ID is not set, or doesn't match a role on the "
            "server. Set it to the id of the bot's own role (Discord assigns "
            "one automatically when it's invited) and rerun."
        )
        return True

    def resolve_members(self) -> None:
        """Map memberships to guild member ids; report the unmatched."""
        self.resolutions = _resolve_members(self.memberships)
        self.report.unresolved = [
            resolution
            for resolution in self.resolutions.values()
            if resolution.member_id is None
        ]

    def resolved_member_ids(self, role: str) -> set[str]:
        """Guild member ids of this session's resolved members with ``role``."""
        return {
            resolution.member_id
            for resolution in self.resolutions.values()
            if resolution.role == role and resolution.member_id
        }

    def all_resolved_member_ids(self) -> set[str]:
        """Guild member ids of every resolved member in this session."""
        return {
            resolution.member_id
            for resolution in self.resolutions.values()
            if resolution.member_id
        }


class DiscordSessionSetup(_DiscordSessionAction):
    """Runs the 'Set up Discord for session' steps.

    ``run()`` defines the production order; each step reads and writes
    instance state, so a test can seed ``role_map``/``resolutions``/
    ``team_role_ids`` directly and exercise one step in isolation.
    """

    def __init__(self, session) -> None:
        super().__init__(session)
        self.report = SetupReport()
        self.team_role_ids: dict[int, str] = {}

    def run(self) -> SetupReport:
        self.load_role_map()
        if (
            self.report_missing_bot_role()
            | self.report_missing_standing_roles()
            | self.report_reserved_team_names()
        ):
            # Fail fast rather than build channels with partial permission
            # lists or team roles adopted from privileged roles; setup is
            # idempotent, so rerunning after fixing the problem is cheap.
            return self.report
        self.ensure_team_roles()
        self.setup_category()
        self.setup_team_channels()
        self.setup_shared_channels()
        self.resolve_members()
        self.assign_member_roles()
        return self.report

    def report_missing_standing_roles(self) -> bool:
        """Report standing roles absent from the guild; truthy aborts the run."""
        missing = [
            name for name in STANDING_ROLES if name.casefold() not in self.role_map
        ]
        for name in missing:
            self.report.errors.append(
                f"Standing role '{name}' does not exist on the Discord server. "
                "Create it manually and rerun."
            )
        return bool(missing)

    def report_reserved_team_names(self) -> bool:
        """Report teams named like a reserved role; truthy aborts the run.

        A team whose name matches a standing or alumni role would make
        ``ensure_team_roles`` adopt that role as the team role, gating the
        team channel on a privileged/shared role. Rename the team and rerun.
        """
        reserved = [
            team for team in self.teams if team.name.casefold() in RESERVED_ROLE_NAMES
        ]
        for team in reserved:
            self.report.errors.append(
                f"Team '{team.name}' has the same name as a reserved Discord role. "
                "Rename the team and rerun."
            )
        return bool(reserved)

    def ensure_team_roles(self) -> None:
        """Create any missing per-team role; team channels gate access by it."""
        self.team_role_ids = {
            team.pk: _ensure_role(team.name, self.role_map, self.report.roles_created)
            for team in self.teams
        }

    def setup_category(self) -> None:
        """Create or adopt the session's category and persist its id.

        A stale stored id (category deleted by hand) falls back to create.
        An existing same-named category is adopted so a manually prepared
        server doesn't end up with duplicates.
        """
        session = self.session
        if session.discord_category_id:
            try:
                discord_client.modify_channel(
                    channel_id=session.discord_category_id,
                    payload={"name": session.short_name},
                )
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    session.discord_category_id = ""
                else:
                    raise
            else:
                self.report.channels_updated.append(session.short_name)
                self.report.category_id = session.discord_category_id
                return

        channels = discord_client.get_guild_channels(guild_id=settings.DISCORD_GUILD_ID)
        existing = next(
            (
                channel
                for channel in channels
                if channel["type"] == CATEGORY_TYPE
                and channel["name"].casefold() == session.short_name.casefold()
            ),
            None,
        )
        if existing is not None:
            category_id = str(existing["id"])
            self.report.channels_updated.append(session.short_name)
        else:
            category = discord_client.create_guild_channel(
                guild_id=settings.DISCORD_GUILD_ID,
                name=session.short_name,
                channel_type=CATEGORY_TYPE,
            )
            category_id = str(category["id"])
            self.report.channels_created.append(session.short_name)

        session.record_discord_category(category_id)
        self.report.category_id = category_id

    def setup_team_channels(self) -> None:
        """Create/update each team's private text and voice channels."""
        for team in self.teams:
            permission_overwrites = [
                _everyone_deny_permission_overwrite(),
                _bot_role_permission_overwrite(),
                _role_permission_overwrite(
                    self.team_role_ids[team.pk], TRUSTED_MEMBER_PERMISSIONS
                ),
                *_grant_permissions_to_roles(
                    self.role_map, SESSION_STAFF_PERMISSIONS, SESSION_ORGANIZERS_ROLE
                ),
            ]
            self._upsert_persisted_channel(
                instance=team,
                id_field="discord_channel_id",
                name=team_channel_name(team),
                permission_overwrites=permission_overwrites,
                channel_type=TEXT_CHANNEL_TYPE,
                error_label=f"the channel for team '{team.name}'",
            )
            self._upsert_persisted_channel(
                instance=team,
                id_field="discord_voice_channel_id",
                name=team_voice_channel_name(team),
                permission_overwrites=permission_overwrites,
                channel_type=VOICE_CHANNEL_TYPE,
                error_label=f"the voice channel for team '{team.name}'",
            )

    def setup_shared_channels(self) -> None:
        """Create/update the captains-and-navigators and announcements channels."""
        shared_channels = [
            (
                "discord_capnav_channel_id",
                CAPNAV_CHANNEL_NAME,
                CAPNAV_CHANNEL_TOPIC,
                [
                    *_grant_permissions_to_roles(
                        self.role_map,
                        TRUSTED_MEMBER_PERMISSIONS,
                        CAPTAINS_ROLE,
                        NAVIGATORS_ROLE,
                        ADVISORS_ROLE,
                    ),
                    *_grant_permissions_to_roles(
                        self.role_map,
                        SESSION_STAFF_PERMISSIONS,
                        ADMINS_ROLE,
                        SESSION_ORGANIZERS_ROLE,
                    ),
                ],
            ),
            (
                "discord_announcements_channel_id",
                ANNOUNCEMENTS_CHANNEL_NAME,
                "",
                [
                    *_grant_permissions_to_roles(
                        self.role_map,
                        TRUSTED_MEMBER_PERMISSIONS,
                        DJANGONAUTS_ROLE,
                        CAPTAINS_ROLE,
                        NAVIGATORS_ROLE,
                        ADVISORS_ROLE,
                    ),
                    *_grant_permissions_to_roles(
                        self.role_map,
                        SESSION_STAFF_PERMISSIONS,
                        ADMINS_ROLE,
                        SESSION_ORGANIZERS_ROLE,
                    ),
                ],
            ),
        ]
        for id_field, name, topic, role_permission_overwrites in shared_channels:
            self._upsert_persisted_channel(
                instance=self.session,
                id_field=id_field,
                name=name,
                permission_overwrites=[
                    _everyone_deny_permission_overwrite(),
                    _bot_role_permission_overwrite(),
                    *role_permission_overwrites,
                ],
                channel_type=TEXT_CHANNEL_TYPE,
                error_label=f"the '{name}' channel",
                topic=topic,
            )

    def _upsert_persisted_channel(
        self,
        *,
        instance,
        id_field: str,
        name: str,
        permission_overwrites: list[dict],
        channel_type: int,
        error_label: str,
        topic: str = "",
    ) -> None:
        """Create or update one channel and persist its id on ``instance``.

        Updating (rather than trusting the stored state) makes reruns
        self-healing: renamed teams and hand-edited permissions converge back
        to the expected configuration. Failures are reported and processing
        continues, one bad channel must not abort the whole run.
        """
        channel_id = getattr(instance, id_field)
        is_text_channel = channel_type == TEXT_CHANNEL_TYPE
        try:
            if channel_id:
                payload = {
                    "name": name,
                    "parent_id": self.report.category_id,
                    "permission_overwrites": permission_overwrites,
                }
                if is_text_channel:
                    payload["topic"] = topic
                    payload["default_auto_archive_duration"] = (
                        THREAD_AUTO_ARCHIVE_MINUTES
                    )
                channel = discord_client.modify_channel(
                    channel_id=channel_id, payload=payload
                )
                self.report.channels_updated.append(name)
            else:
                channel = discord_client.create_guild_channel(
                    guild_id=settings.DISCORD_GUILD_ID,
                    name=name,
                    channel_type=channel_type,
                    parent_id=self.report.category_id,
                    permission_overwrites=permission_overwrites,
                    topic=topic if is_text_channel else "",
                    default_auto_archive_duration=(
                        THREAD_AUTO_ARCHIVE_MINUTES if is_text_channel else None
                    ),
                )
                self.report.channels_created.append(name)
        except requests.HTTPError:
            logger.exception("Failed to set up channel %s", name)
            self.report.errors.append(f"Failed to create/update {error_label}.")
            return
        setattr(instance, id_field, str(channel["id"]))
        instance.save(update_fields=[id_field])

    def assign_member_roles(self) -> None:
        """Give each resolved member their team role and program role.

        Discord has no "add several roles" call, so one PATCH per member
        replaces their full role set with the union of the roles they
        already hold (captured during member resolution) and the roles
        their membership earns. Members who already hold everything are
        skipped entirely.
        """
        for membership in self.memberships:
            resolution = self.resolutions[membership.pk]
            if resolution.member_id is None:
                continue
            role_ids = set()
            if membership.team_id and membership.team_id in self.team_role_ids:
                role_ids.add(self.team_role_ids[membership.team_id])
            standing_role = MEMBERSHIP_DISCORD_ROLES[membership.role]
            if standing_role.casefold() in self.role_map:
                role_ids.add(self.role_map[standing_role.casefold()])
            new_role_ids = role_ids - resolution.guild_role_ids
            if not new_role_ids:
                continue
            try:
                discord_client.modify_guild_member(
                    guild_id=settings.DISCORD_GUILD_ID,
                    user_id=resolution.member_id,
                    payload={"roles": sorted(resolution.guild_role_ids | role_ids)},
                )
            except requests.HTTPError:
                logger.exception(
                    "Failed to assign roles to member %s", resolution.member_id
                )
                self.report.errors.append(
                    f"Failed to assign Discord roles to {resolution.display_name}."
                )
            else:
                self.report.roles_assigned += len(new_role_ids)


class DiscordSessionTeardown(_DiscordSessionAction):
    """Runs the 'Tear down Discord for session' steps.

    Channel access moves from roles to direct member overwrites so the
    program roles can be stripped and reused next session without cutting
    anyone off from their history. Like setup, each step is independently
    testable by seeding instance state.
    """

    def __init__(self, session) -> None:
        super().__init__(session)
        self.report = TeardownReport()
        self.guild_members: list[dict] = []

    def run(self) -> TeardownReport:
        if not self.session.discord_category_id:
            raise ValueError(
                "This session has no Discord category recorded. Run the Discord "
                "setup action first."
            )
        self.load_role_map()
        if self.report_missing_bot_role():
            return self.report
        self.resolve_members()
        self.guild_members = _list_all_guild_members()
        self.archive_channels()
        self.update_member_roles()
        # Release the guild-wide Discord lock now that channels are archived
        # and program roles are freed, letting the next session set up.
        self.session.clear_discord_setup()
        return self.report

    def guild_member_ids_with_role(self, role_name: str) -> set[str]:
        """Guild member ids holding the named role, from the full member list."""
        role_id = self.role_map.get(role_name.casefold())
        if role_id is None:
            return set()
        return {
            member["user"]["id"]
            for member in self.guild_members
            if role_id in member["roles"]
        }

    def archive_channels(self) -> None:
        """Delete team voice channels and switch the rest to direct access."""
        organizers = self.resolved_member_ids(constants.ORGANIZER)
        team_channel_members = {
            team.discord_channel_id: self._team_member_ids(team.pk) | organizers
            for team in self.teams
            if team.discord_channel_id
        }
        # Voice channels have no history worth archiving; delete them.
        voice_channel_teams = {
            team.discord_voice_channel_id: team
            for team in self.teams
            if team.discord_voice_channel_id
        }
        capnav_members = (
            self.resolved_member_ids(constants.NAVIGATOR)
            | self.resolved_member_ids(constants.CAPTAIN)
            | organizers
        )
        admins_and_advisors = self.guild_member_ids_with_role(
            ADMINS_ROLE
        ) | self.guild_member_ids_with_role(ADVISORS_ROLE)
        announcement_members = self.all_resolved_member_ids() | admins_and_advisors
        privileged_users = organizers | admins_and_advisors

        channels = discord_client.get_guild_channels(guild_id=settings.DISCORD_GUILD_ID)
        for channel in channels:
            # Only channels inside the session's category are part of the
            # teardown; everything else on the server is out of scope.
            if str(channel.get("parent_id")) != self.session.discord_category_id:
                continue
            channel_id = str(channel["id"])
            if channel_id in voice_channel_teams:
                self._delete_voice_channel(channel, voice_channel_teams[channel_id])
            elif channel_id in team_channel_members:
                self._archive_channel(channel, team_channel_members[channel_id])
            elif channel_id == self.session.discord_capnav_channel_id:
                self._archive_channel(channel, capnav_members)
            elif (
                self.session.discord_announcements_channel_id
                and channel_id == self.session.discord_announcements_channel_id
            ):
                self._archive_channel(channel, announcement_members)
            else:
                self._archive_channel(channel, privileged_users)

    def _team_member_ids(self, team_pk: int) -> set[str]:
        return {
            self.resolutions[membership.pk].member_id
            for membership in self.memberships
            if membership.team_id == team_pk
            and self.resolutions[membership.pk].member_id
        }

    def archived_channel_name(self, name: str) -> str:
        """Prefix the channel name with the session, e.g. session-7-team-pluto.

        Archived channels outlive the session, so the prefix keeps them
        distinguishable from the next session's identically named channels.
        Already-prefixed names pass through unchanged, keeping teardown
        reruns idempotent.
        """
        prefix = f"{self.session.short_name_slug}-"
        if name.startswith(prefix):
            return name
        return f"{prefix}{name}"

    def _archive_channel(self, channel: dict, retained: set[str]) -> None:
        """Rename with the session prefix and switch to direct member access."""
        archived_name = self.archived_channel_name(channel["name"])
        permission_overwrites = [
            _everyone_deny_permission_overwrite(),
            _bot_role_permission_overwrite(),
        ] + [_member_permission_overwrite(member_id) for member_id in sorted(retained)]
        try:
            discord_client.modify_channel(
                channel_id=str(channel["id"]),
                payload={
                    "name": archived_name,
                    "permission_overwrites": permission_overwrites,
                },
            )
            self.report.channels_processed.append(archived_name)
        except requests.HTTPError:
            logger.exception("Failed to archive channel %s", channel["id"])
            self.report.errors.append(f"Failed to archive channel '{channel['name']}'.")

    def _delete_voice_channel(self, channel: dict, team) -> None:
        try:
            discord_client.delete_channel(channel_id=str(channel["id"]))
            team.clear_discord_voice_channel()
            self.report.channels_deleted.append(channel["name"])
        except requests.HTTPError:
            logger.exception("Failed to delete voice channel %s", channel["id"])
            self.report.errors.append(
                f"Failed to delete the voice channel '{channel['name']}'."
            )

    def update_member_roles(self) -> None:
        """Grant session/alumni roles and strip active program roles guild-wide.

        One PATCH per affected member replaces their full role set: current
        roles, plus the session-title and alumni roles their membership earns,
        minus the four active program roles. Guild members outside the session
        who still hold an active role get the subtraction-only update.
        """
        session_role_id = _ensure_role(
            self.session.title, self.role_map, self.report.roles_created
        )
        past_role_ids = {
            membership_role: _ensure_role(
                role_name, self.role_map, self.report.roles_created
            )
            for membership_role, role_name in PAST_DISCORD_ROLES.items()
        }
        active_role_ids = {
            self.role_map[role_name.casefold()]
            for role_name in MEMBERSHIP_DISCORD_ROLES.values()
            if role_name.casefold() in self.role_map
        }

        additions: defaultdict[str, set[str]] = defaultdict(set)
        for membership in self.memberships:
            member_id = self.resolutions[membership.pk].member_id
            if member_id is None:
                continue
            additions[member_id].update(
                {session_role_id, past_role_ids[membership.role]}
            )

        strip_counts = {role_name: 0 for role_name in MEMBERSHIP_DISCORD_ROLES.values()}
        for member in self.guild_members:
            member_id = member["user"]["id"]
            current_roles = set(member["roles"])
            final_roles = (
                current_roles | additions.get(member_id, set())
            ) - active_role_ids
            if final_roles == current_roles:
                continue
            try:
                discord_client.modify_guild_member(
                    guild_id=settings.DISCORD_GUILD_ID,
                    user_id=member_id,
                    payload={"roles": sorted(final_roles)},
                )
                self.report.members_updated += 1
                for role_name in MEMBERSHIP_DISCORD_ROLES.values():
                    role_id = self.role_map.get(role_name.casefold())
                    if role_id in current_roles:
                        strip_counts[role_name] += 1
            except requests.HTTPError:
                logger.exception("Failed to update roles for member %s", member_id)
                self.report.errors.append(
                    f"Failed to update Discord roles for member id {member_id}."
                )
        self.report.roles_stripped = strip_counts
