# PostGIS & Docker Migration Guide

This documents the steps needed to migrate the Dokku-managed staging and
production servers when the 3D talks map feature landed. That feature introduced
a `PointField` on the `Talk` model, which requires the PostGIS extension and the
GDAL system library.

The existing Dokku postgres service uses a plain PostgreSQL image that does not
include the PostGIS binaries. A new PostGIS-enabled service must be created
alongside the existing one. The old service is left intact until the new one is
confirmed working. **Perform the migration on staging first and verify it before
touching production.**

For local development setup, see the [README](../../README.md).

---

## Staging migration

> **Note on automatic restarts:** The `Procfile` release phase runs
> `scripts/release.sh`, which calls `manage.py migrate`. Every
> `dokku config:set` and `postgres:link`/`unlink` call can restart the app and
> trigger that release phase. Use `--no-restart` throughout and let the final
> deploy be the single controlled restart with everything configured correctly.

### 1. Export staging data

```bash
ssh root@djangonaut.space
dokku postgres:export staging > /tmp/staging-backup.dump
```

### 2. Create a new PostGIS service alongside the existing one

```bash
dokku postgres:create staging-postgis --image "postgis/postgis" --image-version "17-3.5"
```

### 3. Enable the PostGIS extension

```bash
dokku postgres:connect staging-postgis
```

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
\q
```

### 4. Restore the data into the new service

```bash
dokku postgres:import staging-postgis < /tmp/staging-backup.dump
```

### 5. Switch the app to the new service

`unlink` removes `DATABASE_URL` entirely, which would cause a broken restart.
Suppress it. `link` sets a valid `DATABASE_URL` to the new service and should
restart normally — `settings.py` hardcodes the PostGIS engine so the `postgres://`
scheme Dokku uses is not a problem:

```bash
dokku postgres:unlink staging staging --no-restart
dokku postgres:link staging-postgis staging
```

### 6. Update `DJANGO_SETTINGS_MODULE`

The settings package was consolidated into a single `indymeet/settings.py`:

```bash
dokku config:set staging DJANGO_SETTINGS_MODULE=indymeet.settings --no-restart
```

### 7. Switch staging to the Dockerfile builder

The `Dockerfile` installs `libgdal-dev` and `gdal-bin` at build time. Dokku
must use the Dockerfile rather than the Heroku buildpack to pick this up:

```bash
dokku builder:report staging  # verify current builder
dokku builder:set staging selected dockerfile
```

### 8. Deploy

Merge to develop to trigger a deployment.

### 9. Verify staging

Confirm the site loads, the talks map renders, and the admin works.

### 10. Remove the old staging service

Once staging is confirmed working:

```bash
dokku postgres:destroy staging --force
```

---

## Production migration

Once staging is verified, repeat the same steps for production.

### 1. Export production data

```bash
dokku postgres:export djangonaut-space > /tmp/production-backup.dump
```

### 2. Create a new PostGIS service alongside the existing one

```bash
dokku postgres:create djangonaut-space-postgis --image "postgis/postgis" --image-version "17-3.5"
```

### 3. Enable the PostGIS extension

```bash
dokku postgres:connect djangonaut-space-postgis
```

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
\q
```

### 4. Restore the data into the new service

```bash
dokku postgres:import djangonaut-space-postgis < /tmp/production-backup.dump
```

### 5. Switch the app to the new service

```bash
dokku postgres:unlink djangonaut-space djangonaut-space --no-restart
dokku postgres:link djangonaut-space-postgis djangonaut-space
```

### 6. Update `DJANGO_SETTINGS_MODULE`

```bash
dokku config:set djangonaut-space DJANGO_SETTINGS_MODULE=indymeet.settings --no-restart
```

### 7. Switch production to the Dockerfile builder

```bash
dokku builder:report djangonaut-space  # verify current builder
dokku builder:set djangonaut-space selected dockerfile
```

### 8. Deploy

Create the release to main to trigger the production deployment.

### 9. Verify production

Confirm the site loads, the talks map renders, and the admin works.

### 10. Remove the old production service

Once production is confirmed working:

```bash
dokku postgres:destroy djangonaut-space --force
```

---

## Settings consolidation reference

The `indymeet/settings/` package (`base.py`, `dev.py`, `test.py`,
`production.py`) was replaced by a single `indymeet/settings.py`. Behaviour
previously controlled by importing different modules is now controlled by
environment variables:

| Old mechanism | New mechanism |
|---------------|---------------|
| `indymeet.settings.production` — Sentry | `SENTRY_DNS` env var |
| `indymeet.settings.production` — email backend | `EMAIL_BACKEND` env var |
| `DEBUG=True` hardcoded in `dev.py` | `DEBUG` env var |
| `DJANGO_SETTINGS_MODULE=indymeet.settings.test` | `DJANGO_SETTINGS_MODULE=indymeet.settings` |
| `postgis://` scheme required in `DATABASE_URL` | `engine` hardcoded in `dj_database_url.config()` — Dokku's `postgres://` scheme works as-is |
