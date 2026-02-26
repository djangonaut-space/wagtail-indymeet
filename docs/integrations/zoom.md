# Zoom Integration

## Overview

The platform integrates with Zoom to manage meeting creation and management for sessions and events. This uses a **Server-to-Server OAuth** app, which allows the application to authenticate as itself (rather than on behalf of a user) and call the Zoom API without requiring a user login flow.

## App Credentials

The Zoom app is named **Djangonaut Space Toolkit** and can be reviewed or managed at:

https://marketplace.zoom.us/develop/apps/

## Server-to-Server OAuth

We use Zoom's Server-to-Server OAuth (S2S OAuth) app type. Unlike a standard OAuth flow, S2S OAuth generates a token directly from app credentials — there is no browser redirect or user consent step. This makes it suitable for backend/server use.

Reference: https://developers.zoom.us/docs/internal-apps/s2s-oauth/#get-app-credentials

### Required Credentials

Three values are needed from the Zoom app dashboard and must be set as environment variables in the `.env` file locally or in the environment in production.

| Variable | Description |
|---|---|
| `ZOOM_ACCOUNT_ID` | The Zoom account ID associated with the app |
| `ZOOM_CLIENT_ID` | The client ID from the app credentials page |
| `ZOOM_CLIENT_SECRET` | The client secret from the app credentials page |

### Scopes

The following scope must be granted in the Zoom app dashboard under the **Scopes** tab:

| Scope | Reason |
|---|---|
| `meeting:write:meeting:admin` | Create meetings on behalf of users in the account (`POST /users/{userId}/meetings`) |
