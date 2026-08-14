# Buttondown Integration

## Overview

The platform integrates with [Buttondown](https://buttondown.com) to sync site users to a newsletter subscriber list. Tags reflect each user's roles, session history, and interests for list segmentation.

## App Credentials

The Buttondown account can be managed at: https://buttondown.com/settings

## Required Credentials

### API Key

Retrieve the API key from **Settings → API** in the Buttondown dashboard.

| Variable | Description |
|---|---|
| `BUTTONDOWN_API_KEY` | API key from the Buttondown settings page |

Set this in the `.env` file locally or as an environment variable in production. If unset or empty the integration is disabled.

### Webhook Secret

The platform exposes a webhook endpoint at `/webhooks/buttondown/` that Buttondown uses to notify the platform when a subscriber unsubscribes.

To set it up:

1. Go to **Settings → Webhooks** in the Buttondown dashboard.
2. Add the production URL: `https://djangonaut.space/webhooks/buttondown/`
3. Enable the **subscriber.unsubscribed** event.
4. Copy the generated webhook secret.

### Subscriber ID Formats

Buttondown subscriber IDs come in two formats depending on the API version:

- **Prefixed format:** `sub_<crockford-base32-encoded-uuid>` (e.g. `sub_5anaxvqk6cvqeyxvqzzynanexv`)
- **Raw UUID format:** `aaaabbbb-cccc-dddd-eeee-ffffaaaabbbb`

The webhook handler transparently normalizes both formats to a UUID before looking up the user.

| Variable | Description |
|---|---|
| `BUTTONDOWN_WEBHOOK_SECRET` | Signing secret used to verify incoming webhook requests |

## Bulk Initial Sync

To sync all existing active users when first enabling the integration:

```bash
# Preview which users would be synced
uv run python manage.py sync_buttondown --dry-run

# Enqueue sync tasks for all active users
uv run python manage.py sync_buttondown
```

Ongoing syncs are handled automatically on every user profile save.

## IP Address on Subscription

Buttondown's subscriber-creation endpoint accepts an `ip_address` field, used for location detection and legitimacy validation. When a user confirms their account (activates their account), the view stashes the IP address as a transient, non-persisted attribute (`_buttondown_ip_address`) on the `UserProfile` instance before saving. The `post_save` signal handle queues a task to sync the buttondown subscription.

The flow: the view reads the client IP via `get_client_ip()` (`home/utils.py`) and stashes it as a transient, non-persisted attribute (`_buttondown_ip_address`) on the `UserProfile` instance before saving. The `post_save` signal handler (`accounts/receivers.py`) reads that attribute off the instance and forwards it through `sync_user_to_buttondown.enqueue()` -> `ButtondownService.sync_user()` -> `ButtondownClient.create_subscriber()`. It's only ever sent when a *new* Buttondown subscriber is being created — existing subscribers are updated via PATCH, which doesn't use this field. The IP is never persisted to our own database.
