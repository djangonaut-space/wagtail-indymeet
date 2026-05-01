# Cloudflare Integration

## Overview

The platform uses Wagtail's built-in frontend cache purging to automatically invalidate Cloudflare's CDN cache when pages are published or deleted. No additional Python packages are required.

Reference: https://docs.wagtail.org/en/latest/reference/contrib/frontendcache.html#cloudflare

## Configuration

Two environment variables must be set in production:

| Variable | Description |
|---|---|
| `CLOUDFLARE_ZONE_ID` | The zone ID for the domain, found in the Cloudflare dashboard under **Overview** |
| `CLOUDFLARE_BEARER_TOKEN` | A Cloudflare API token scoped to **Zone › Cache Purge** |

If either variable is absent, cache purging is silently disabled — there is no error.

## Creating the API Token

1. In the Cloudflare dashboard, go to **My Profile › API Tokens**.
2. Click **Create Token** and use the **Edit zone** template, or create a custom token with a single permission: **Zone › Cache Purge › Purge**.
3. Scope the token to the relevant zone (djangonaut.space).
4. Copy the generated token and set it as `CLOUDFLARE_BEARER_TOKEN`.

## Deployment

Set the variables in Dokku:

```bash
dokku config:set <app> CLOUDFLARE_ZONE_ID=... CLOUDFLARE_BEARER_TOKEN=...
```
