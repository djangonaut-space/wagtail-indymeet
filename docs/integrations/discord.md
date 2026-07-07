# Discord Integration

## Overview

The platform integrates with Discord in two ways, both using **bot-token authentication** (no OAuth flow — the bot authenticates as itself):

1. **Scheduled-event sync** — published events with a Zoom link are mirrored as Discord scheduled events (see `home/tasks/sync_event.py`).
2. **Session channel and role management** — admin actions on the Session changelist create the per-session channel category, team channels, and role assignments at the start of a session, and archive them at the end.

## App Credentials

The bot is managed in the Discord Developer Portal:

https://discord.com/developers/applications

The bot must be invited to the Djangonaut Space server (guild) with the permissions listed below.

## Required Credentials

| Variable | Description |
|---|---|
| `DISCORD_BOT_TOKEN` | The bot's token, copied from the **Token** section of the app's **Bot** page in the developer portal (click **Reset Token** if none is shown) |
| `DISCORD_GUILD_ID` | The Discord server (guild) ID; enable Developer Mode in Discord, right-click the server, and choose "Copy Server ID" |
| `DISCORD_BOT_ROLE_ID` | The id of the bot's own role on the server (Discord creates this automatically when the bot is invited with the `bot` scope); with Developer Mode on, right-click the role in **Server Settings → Roles** and choose "Copy Role ID". Required for the session setup/teardown actions — see [The Bot's Own Role](#the-bots-own-role) |

Set these in the `.env` file locally or as environment variables in production. If `DISCORD_BOT_TOKEN` or `DISCORD_GUILD_ID` is unset or empty the integration is disabled (`discord_enabled()` returns `False`) and the admin actions refuse to run. If `DISCORD_BOT_ROLE_ID` is unset or doesn't match a role on the server, setup/teardown report the problem and abort before touching Discord.

## Bot Permissions

Grant the bot these permissions when inviting it (or via a role):

| Permission | Reason |
|---|---|
| Manage Channels | Create/update the session category and channels, edit permission overwrites |
| Manage Roles | Create team/session/alumni roles and assign/remove member roles |
| Manage Events | Create and update scheduled events (event sync) |
| View Channels, Send Messages, Embed Links, Attach Files, Add Reactions, Use External Emoji, Use External Stickers, Read Message History, Create Public Threads, Create Private Threads, Send Messages in Threads, Pin Messages, Send Voice Messages, Send Polls, Manage Messages, Manage Threads | Channel setup writes overwrites that *allow* these to team/staff roles — Discord only lets the bot allow a permission it holds itself, so without these on the bot's own role, channel creation fails with `403 Missing Permissions` (see `TRUSTED_MEMBER_PERMISSIONS`/`SESSION_STAFF_PERMISSIONS` in `home/integrations/discord/session_service.py`) |

**Role hierarchy caveat:** Discord only lets the bot manage roles *below its own highest role*. Keep the bot's role above every role it manages (team roles, `Djangonauts`, `Captains`, `Navigators`, `Session Organizers`, session-title roles, `past *`, `stars`), otherwise those calls fail with a 403.

## Inviting the Bot to a Server

The bot token authenticates the app, but it doesn't put the bot *in* a server — that requires a one-time OAuth2 invite:

1. In the Developer Portal, open the app's **OAuth2 → URL Generator** page.
2. Under **Scopes**, check `bot`.
3. Under **Bot Permissions**, check every permission listed in [Bot Permissions](#bot-permissions) above.
4. Copy the generated URL and open it in a browser, then pick the target server and authorize.
5. In the server's role list, drag the bot's role above every role it manages (see the caveat above).

## The Bot's Own Role

Every channel setup/teardown manage denies `@everyone` and grants view access only to specific named roles (a team role, `Session Organizers`, direct member overwrites, ...). Discord only bypasses per-channel overwrites for **Administrator** — a guild-wide permission like Manage Channels does not — so without an explicit grant, the bot loses visibility into a channel the moment it's created, and later modify/delete calls fail with `403 Missing Access` even though the bot has Manage Channels.

To avoid requiring Administrator, this module adds the bot's own role to every channel's permission overwrites automatically. Set `DISCORD_BOT_ROLE_ID` to that role's id (see [Required Credentials](#required-credentials)); setup and teardown both check it's set and matches a real role before making any changes.

## Privileged Intents

Enable the **Server Members Intent** (`GUILD_MEMBERS`) on the app's **Bot** page. The teardown action lists all guild members to find role holders; that endpoint requires the intent. (The member *search* used to resolve usernames does not.)

## Guild Role Conventions

The session actions look roles up by name (case-insensitively). These standing roles must already exist on the server — if any are missing, setup stops before making changes and reports them, rather than creating them:

- `Djangonauts`, `Captains`, `Navigators`, `Session Organizers`, `Admins`, `Advisors`

These roles are created automatically when missing:

- One role per team, named exactly after the team (setup)
- One role per session, named after the session title (teardown)
- `Past Navigators`, `Past Captains`, `Past Session Organizers`, `stars` (teardown)

The expected names are defined as constants in `home/integrations/discord/session_service.py`.

### Bootstrapping a test server

Because setup refuses to run when the standing roles are missing, exercising
the integration locally means creating those roles on a throwaway server
first. The `bootstrap_discord_server` management command does that:

```bash
python manage.py bootstrap_discord_server
```

It targets whatever guild is configured in `DISCORD_GUILD_ID` and only runs
when `ENVIRONMENT=dev` (the local default), so it can never touch production.
It creates the standing roles plus the alumni roles (`Past Navigators`, `Past
Captains`, `Past Session Organizers`, `stars`), and is idempotent — roles that
already exist (matched case-insensitively) are skipped.

To get a working local setup:

1. Create a Discord server (or reuse a throwaway one) and invite your bot with
   the [permissions above](#bot-permissions).
2. Set `DISCORD_BOT_TOKEN`, `DISCORD_GUILD_ID`, and `DISCORD_BOT_ROLE_ID` in
   `.env` for that server.
3. Run `bootstrap_discord_server` to create the standing/alumni roles.
4. In Discord, drag the bot's role above every role it manages.
5. Enable the **Server Members Intent** on the bot.
6. Set Discord usernames on the profiles of any users you'll test with.

Then the Session admin's setup/teardown actions run against the test server.

## Admin Usage

The actions live in the **Discord** column of the Session changelist (Django admin), and are restricted to superusers and the session's organizers.

Setup and teardown run as background tasks (`home/tasks/discord_session.py`) — the orchestration makes far too many Discord API calls for a request. Confirming the action enqueues the task and returns to the changelist; when the task finishes, the requesting user gets an email with the report (channels/roles touched, errors, and members that couldn't be matched to a Discord account). If the run had errors, superusers are CCed on that email so an admin can help fix the server.

**Only one session may have Discord set up at a time.** Because teardown strips program roles from the whole server, an overlapping active session would lose access to its own channels. Setup and teardown both refuse to run while another session still has a Discord category recorded — tear the previous session down first. Teardown clears the category ID when it finishes, releasing the lock for the next session.

### Set up Discord

Setup is idempotent — rerunning it converges channels, names, permissions, and topics back to the expected state, so it's the fix for hand-edited or renamed channels. Channel/category IDs are stored on the Session and Team records.

Any organizing channel the organizers want inside the category is created manually in Discord; teardown will handle it.

### Team messages

The **Team messages** link on the changelist (also linked from the setup-complete email) shows a copy/paste welcome message per team channel — mentions, team page link, and Drive folder. It's generated from the database on request, so it can be revisited at any time and reflects membership changes made after setup.

### Tear down Discord

Run when the session ends.

Teardown requires setup to have run first (it needs the stored category ID) and is hard to undo — the confirmation page spells out the scope before anything happens.
