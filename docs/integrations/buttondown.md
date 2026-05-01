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
