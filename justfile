# Djangonaut Space - development helpers
# Requires: https://github.com/casey/just

django := "docker compose exec django"

# Start all services
up:
    docker compose up

# Start all services in the background
up-detached:
    docker compose up -d

# Stop all services
down:
    docker compose down

# Follow Django logs
logs:
    docker compose logs -f django

# Open a Django shell
shell:
    {{django}} uv run python manage.py shell

# Open a database shell
dbshell:
    {{django}} uv run python manage.py dbshell

# Create a superuser
superuser:
    {{django}} uv run python manage.py createsuperuser

# Run database migrations
migrate *args:
    {{django}} uv run python manage.py migrate {{args}}

# Create new migrations
makemigrations *args:
    {{django}} uv run python manage.py makemigrations {{args}}

# Run all tests (excluding Playwright)
test *args:
    {{django}} uv run pytest {{args}}

# Run tests with database reuse
test-fast *args:
    {{django}} uv run pytest --reuse-db {{args}}

# Install Playwright browsers and run Playwright tests
test-playwright *args:
    {{django}} uv run playwright install --with-deps
    {{django}} uv run pytest -m playwright {{args}}

# Run Playwright tests in headed mode (visible browser)
test-playwright-headed *args:
    {{django}} uv run pytest -m playwright --headed {{args}}

# Install Tailwind dependencies
tailwind-install:
    {{django}} uv run python manage.py tailwind install

# Start Tailwind CSS watcher
tailwind-start:
    {{django}} uv run python manage.py tailwind start

# Build Tailwind CSS for production
tailwind-build:
    {{django}} uv run python manage.py tailwind build

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
