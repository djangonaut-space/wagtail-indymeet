# Google Calendar Integration

## Overview

Users can connect their **Google Calendar** so that the platform can read their
**free/busy** times and reconcile them with the weekly availability grid.

Unlike the Zoom and Discord integrations (which use a single app-level
credential), Google Calendar uses a **per-user OAuth 2.0 authorization-code
flow**: each user grants access to their own calendar, and we store their tokens
(encrypted) against their account.

## Privacy: free/busy only

Busy times are always derived from the
`https://www.googleapis.com/auth/calendar.freebusy` scope, which returns only
*when* a user is busy — **never event titles, attendees, or descriptions** — and
we persist only start/end intervals. The `openid`/`email` scopes are requested
solely to label the connected account in the UI.

We also request `https://www.googleapis.com/auth/calendar.events.readonly`. This
is **not** used to read events — it is required by Google purely to register
`events.watch` push notifications (webhooks). The notification carries no event
data; it only signals that the calendar changed, at which point we re-query
free/busy. When webhooks are disabled (`GOOGLE_CALENDAR_WEBHOOK_ENABLED` unset)
the scope is granted but never exercised, and freshness comes from polling + lazy
refresh instead.

## Google Cloud setup (operations)

You need a Google Cloud project with an OAuth client. Manage it at
<https://console.cloud.google.com/>.

1. **Create/choose a project** for Djangonaut Space.
2. **Enable the Google Calendar API**
   (APIs & Services → Library → "Google Calendar API" → Enable).
3. **Configure the OAuth consent screen**
   (APIs & Services → OAuth consent screen):
   - User type: **External**.
   - Fill in app name, support email, developer contact, the app homepage
     (`https://djangonaut.space`), and privacy-policy links.
   - Add the scopes `.../auth/calendar.freebusy` and
     `.../auth/calendar.events.readonly` (plus `openid`, `email`).
   - See **Verification & testing mode** below.
4. **Create an OAuth Client ID**
   (APIs & Services → Credentials → Create credentials → OAuth client ID):
   - Application type: **Web application**.
   - **Authorized redirect URIs** — add one per environment, exactly matching
     `BASE_URL` + `/accounts/availability/calendar/google/callback/`:
     - `https://djangonaut.space/accounts/availability/calendar/google/callback/`
     - `https://staging.djangonaut.space/accounts/availability/calendar/google/callback/`
     - `http://localhost:8000/accounts/availability/calendar/google/callback/` (local)
   - Copy the **Client ID** and **Client secret** into the env vars below.

The redirect URI must match byte-for-byte, including the trailing slash. It is
derived from `settings.BASE_URL`, so make sure `BASE_URL` is correct in each
environment.

### Domain verification (webhooks only)

Push notifications require the notification URL's domain to be **verified and
registered** for your project. If you plan to enable webhooks
(`GOOGLE_CALENDAR_WEBHOOK_ENABLED`), verify each webhook domain
(`djangonaut.space`, `staging.djangonaut.space`) via **Google Search Console**
and add it under **APIs & Services → Domain verification** in the Cloud console.
`localhost` cannot be verified, which is why webhooks stay off locally.

### Verification & testing mode

`calendar.freebusy` and `calendar.events.readonly` are **sensitive scopes**.
Google requires the OAuth app to pass **verification** before unaffiliated users
can grant access:

- **Testing mode** (default): works immediately, but only for **test users you
  add manually** on the consent screen (max 100). Their consent screen shows an
  "unverified app" warning. This is fine for a small cohort or a pilot.
- **In production / verified**: submit the app for Google's OAuth verification
  (adds branding + a security review). Required to serve arbitrary users without
  the warning.

Plan to run in testing mode with allow-listed users first, then submit for
verification when you want to open it to everyone.

## Environment variables

Set these in `.env` locally / the environment in production. Leaving the client
ID/secret unset **disables** the integration (the "Connect Google Calendar"
button is hidden and the overlap toggle simply subtracts nothing).

| Variable | Description |
|---|---|
| `GOOGLE_OAUTH_CLIENT_ID` | OAuth client ID from Google Cloud Credentials |
| `GOOGLE_OAUTH_CLIENT_SECRET` | OAuth client secret |
| `CALENDAR_TOKEN_ENCRYPTION_KEY` | Fernet key used to encrypt stored tokens (see below) |
| `GOOGLE_CALENDAR_WEBHOOK_ENABLED` | Set (to any non-empty value) to register push-notification channels. **Opt-in per environment** — enable on staging/production once their domains are verified; leave unset in local Docker/CI (both run as `ENVIRONMENT=production` against `localhost`, where `events.watch` cannot reach us). When unset, freshness comes from polling + lazy refresh. |

### Token encryption key

Refresh tokens grant ongoing calendar access, so they are **encrypted at rest**
with Fernet (`availability/fields.py`). Generate a key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

- Set the result as `CALENDAR_TOKEN_ENCRYPTION_KEY`.
- If unset, a **throwaway key is generated at startup** so local/dev/test work
  out of the box — but it changes on every restart, so stored tokens become
  unreadable. In **production with the Google integration enabled**, the app
  refuses to start without a stable key.
- **Rotation:** there is no re-encryption step. Rotating the key makes existing
  stored tokens unreadable; affected users simply reconnect (the flow tolerates
  a failed refresh and prompts a reconnect). If you rotate, expect users to
  reconnect their calendars.

## Data model

`CalendarConnection` (one row per connected Google account, unique on
`(user, account_label)`, so a user can connect more than one account):

| Field | Notes |
|---|---|
| `account_label` | Google account email; identifies the connection and shown in the UI |
| `access_token` / `refresh_token` | **Encrypted**; access token auto-refreshed |
| `token_expiry` | When the access token expires |
| `scopes` | Granted scopes |
| `last_synced_at` | Last **successful** sync |
| `last_sync_attempted_at` | Last sync attempt (success or failure) |
| `synced_until` | How far into the future cached busy periods reach (~30 days) |
| `last_sync_error` | Last error message; empty ⇒ healthy |
| `webhook_channel_id` / `webhook_resource_id` | Google push-notification channel identifiers |
| `webhook_channel_token` | **Encrypted** shared secret verified on incoming notifications |
| `webhook_expires_at` | When the channel expires and must be renewed |

`CalendarBusyPeriod` (cached concrete busy intervals, one row per busy block):

| Field | Notes |
|---|---|
| `connection` | FK to `CalendarConnection` (CASCADE) |
| `start` / `end` | UTC interval. **Only** start/end are stored — never event details |

Encrypted credentials and the webhook secret are intentionally excluded from the
Django admin; sync-metadata fields are shown read-only for observability.

## How the week is chosen

Availability is a *recurring weekly* pattern (UTC, Sunday-anchored), but calendar
events are date-specific. Both features use the **current week, starting from
today** (earlier days in the week are never touched) through the coming Sunday,
and project that week's busy intervals onto the recurring grid. The UI always
labels the concrete window it used (e.g. "Jul 12 – Jul 18").

## Syncing & caching

Busy times live in `CalendarBusyPeriod` rows; reads (import, overlap) only ever
query the database — never Google. Each sync (`service.sync_connection`) fetches
the **next ~30 days** of free/busy, replaces the connection's stored future
periods, and prunes anything ending more than **7 days** ago. The cache is kept
fresh by three paths, all funnelling through the same routine:

- **Webhooks** (when enabled): Google POSTs to
  `/accounts/availability/calendar/google/webhook/`; the view verifies the
  channel token and enqueues a background sync. Channels are registered on
  connect and renewed (before expiry) during any sync.
- **Polling:** the `sync_calendars` management command enqueues a sync for every
  connection and prunes old data. Run it periodically (see below).
- **Lazy refresh:** loading the overlap page enqueues a background sync for any
  connection whose data is older than `SYNC_STALE_AFTER` (6h), so the next view
  is fresh. The manual **Import** button syncs synchronously for immediate results.

A `CalendarSyncError` during a background/polling sync is recorded on
`last_sync_error` and never breaks a page — reads fall back to the last-good
cached data (or the user's saved availability).

### Scheduling the poll

There is no scheduler wired up in the repo yet (the `django-tasks` worker only
runs enqueued jobs). Configure a periodic trigger for
`python manage.py sync_calendars` — e.g. a Dokku cron entry or a GitHub Actions
`schedule:` workflow — ideally every few hours. Webhooks handle real-time
updates; polling is the safety net that also renews channels and prunes data.

## User flows

- **Connect:** availability page → *Connect Google Calendar* → Google consent →
  redirected back; a `CalendarConnection` is created/updated.
- **Import:** availability page → *Import busy times* → conflicting cells are
  deselected client-side; the user reviews and presses **Save** to persist.
  Nothing is saved automatically.
- **Overlap:** Compare Availability page → tick *Subtract connected calendars* →
  the grid reloads with each connected user's busy times removed.
- **Disconnect:** availability page → *Disconnect* → the push-notification
  channel is stopped (best-effort) and the `CalendarConnection` — along with its
  cached `CalendarBusyPeriod` rows (CASCADE) — is deleted. To also revoke
  Google's grant, users can remove access at
  <https://myaccount.google.com/permissions>.

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| "Connect Google Calendar" not shown | `GOOGLE_OAUTH_CLIENT_ID`/`SECRET` unset. |
| `redirect_uri_mismatch` from Google | Redirect URI not registered, or `BASE_URL` differs (scheme/host/trailing slash). |
| App refuses to start in production | `CALENDAR_TOKEN_ENCRYPTION_KEY` unset while Google is enabled. |
| Import says "reconnect" | Refresh token missing/expired, or the encryption key changed. User reconnects. |
| "Unverified app" warning | App is in testing mode; add the user as a test user or complete verification. |
| Overlap toggle changes nothing | None of the selected users have a connected calendar, or their cache hasn't synced yet (expected). |
| Busy times look stale | Check `last_sync_error`/`last_synced_at` in the admin. Ensure the `django-tasks` worker is running and `sync_calendars` is scheduled. |
| Webhooks never fire | `GOOGLE_CALENDAR_WEBHOOK_ENABLED` unset, domain not verified, or `BASE_URL` not publicly reachable over HTTPS. Polling/lazy refresh still keep data fresh. |
