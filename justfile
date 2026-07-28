# Djangonaut Space - development helpers
# Requires: https://github.com/casey/just

django := "docker compose exec django"

# Name of the migrated template database Postgres clones for Playwright test
# database creation instead of replaying every migration (see indymeet/settings.py).
test_db_template := "template_wagtail_indymeet_test"
django_playwright := "docker compose exec -e TEST_DB_TEMPLATE=" + test_db_template + " django"

# Start all services in the background with file watching. Pass --attached to stream logs in the foreground instead.
up attached="":
    docker compose {{ if attached == "--attached" { "up --watch" } else { "watch" } }}

# Stop all services
down:
    docker compose down

# Follow Django and worker logs
logs:
    docker compose logs -f django worker

# Open a Django shell
shell:
    {{django}} uv run python manage.py shell_plus

# Create a superuser
superuser:
    {{django}} uv run python manage.py createsuperuser

# Run database migrations
migrate *args:
    {{django}} uv run python manage.py migrate {{args}}

# Show database migration sql
sqlmigrate *args:
    {{django}} uv run python manage.py sqlmigrate {{args}}

# Create new migrations
makemigrations *args:
    {{django}} uv run python manage.py makemigrations {{args}}

# Open a database shell
dbshell:
    {{django}} uv run python manage.py dbshell

# Create a demo session
bootstrap_session:
    {{django}} uv run python manage.py generate_sample_session

# Bootstrap a Discord server
bootstrap_discord:
    {{django}} uv run python manage.py bootstrap_discord_server

# Build/refresh the migrated template database used to speed up Playwright test database
# creation. Skips the rebuild when the template already reflects every migration, so it's
# safe to run unconditionally; test-playwright/test-playwright-headed do this automatically.
build-test-db-template *args:
    {{django_playwright}} uv run python manage.py build_test_db_template {{args}}

# Run all tests (excluding Playwright)
test *args:
    {{django}} uv run pytest -n auto {{args}}

# Install Playwright browsers and run Playwright tests
test-playwright *args:
    {{django}} uv run playwright install --with-deps
    just build-test-db-template {{ if args =~ '--create-db' { "--force" } else { "" } }}
    {{django_playwright}} uv run pytest -m playwright -n auto {{args}}

# Run Playwright tests in headed mode (visible browser)
test-playwright-headed *args:
    just build-test-db-template {{ if args =~ '--create-db' { "--force" } else { "" } }}
    {{django_playwright}} uv run pytest -m playwright --headed {{args}}

# Install Tailwind dependencies
tailwind-install:
    {{django}} uv run python manage.py tailwind install

# Start Tailwind CSS watcher
tailwind-start:
    {{django}} uv run python manage.py tailwind start

# Dump database fixtures (excludes system tables)
dumpdata:
    {{django}} uv run python manage.py dumpdata \
        --natural-foreign --indent 2 \
        -e contenttypes \
        -e auth.permission \
        -e wagtailcore.groupcollectionpermission \
        -e wagtailcore.grouppagepermission \
        -e wagtailimages.rendition \
        -e sessions \
        -e admin \
        -e wagtailsearch.indexentry \
        -e accounts.userprofile \
        -o fixtures/data.json

# Load fixtures
loaddata:
    {{django}} uv run python manage.py loaddata fixtures/data.json

# Add a main dependency
add package:
    {{django}} uv add {{package}}

# Add a dev dependency
add-dev package:
    {{django}} uv add --group dev {{package}}

# Add a test dependency
add-test package:
    {{django}} uv add --group test {{package}}

# Upgrade all dependencies
upgrade:
    {{django}} uv lock --upgrade

# Upgrade a specific package
upgrade-package package:
    {{django}} uv lock --upgrade-package {{package}}

# Run pre-commit hooks on all files
lint:
    {{django}} uv run pre-commit run --all-files

# Run zizmor security checks on GitHub Actions workflows
zizmor:
    uvx zizmor .github/workflows/

# Collect static files
collectstatic:
    {{django}} uv run python manage.py collectstatic --no-input
