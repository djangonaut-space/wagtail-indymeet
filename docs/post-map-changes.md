# Post-Map Page Setup (For Existing DB Users)

After pulling the branch with the map page, follow these steps if you have **existing PostgreSQL data**.

## Changes Made

- **Dockerfile**: Added `libgdal-dev g++ gdal-bin libpq-dev` for GDAL compilation
- **pyproject.toml**: Added GDAL pinned to `3.6.2` (matches Debian bookworm)
- **docker-compose.yml**: Database image changed from `postgres:17` to `postgis/postgis:17-3.5` (include PostGIS binaries) -
**Image change doesn't touch your data, your volume mount stays identical**
- **`.env.template.local`, `.env.template`, `.env.template.docker`**: Have the `DATABASE_URL` changed from `postgres://` to **`postgis://`**
- **Django migrations**: `home/migrations/0049_talk_talkspeaker.py` automatically runs `CREATE EXTENSION IF NOT EXISTS postgis;` during `python manage.py migrate` - **no manual psql command needed**

Note: The postgres:// → postgis:// change was updated across ALL active config files (`.env` templates, `.github/workflows/tests.yml`, etc.) except `docs/archive/hetzner-migration.md` (archived doc).

## Required Actions (Preserves Your Data)
### ⚠️ Update Your .env File
#### Copy the **NEW** template to update DATABASE_URL:
Copy in Linux:
```sh
cp .env.template.local .env
```
Copy in Windows:
```sh
copy .env.template.local .env
```

#### Check the `DATABASE_URL` variable change in the .env:
from:
```
DATABASE_URL=postgres://djangonaut:djangonaut@localhost:5432/djangonaut-space
```
to:
```
DATABASE_URL=postgis://djangonaut:djangonaut@localhost:5432/djangonaut-space
```


## ⚠️ NEW: Install System Libraries (Non-Docker Users)

### **Map page requires GDAL/PostGIS libraries:**

**Linux (Debian/Ubuntu):**
```sh
sudo apt install libgdal-dev gdal-bin libpq5
```

## If using Docker:
### Rebuild & Restart Services
```sh
docker compose build --no-cache  # Rebuilds with GDAL libraries
docker compose up -d db          # Restart DB with PostGIS image
```

### Fix Collation Mismatch (One-time)
Collation fix is a one-time operation - handle it manually after switching images:
```sh
docker compose exec db psql -U djangonaut -d djangonaut -c "ALTER DATABASE djangonaut REFRESH COLLATION VERSION;"
```

### OPTIONAL - Silence template1 and postgres warnings:
```sh
docker compose exec db psql -U djangonaut -d template1 -c "ALTER DATABASE template1 REFRESH COLLATION VERSION;"
docker compose exec db psql -U djangonaut -d postgres -c "ALTER DATABASE postgres REFRESH COLLATION VERSION;"
```

### Start Full Stack
```sh
docker compose up -d
```
