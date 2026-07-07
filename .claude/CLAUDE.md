# Djangonaut Space - Shared Claude Context

## Project Overview

Djangonaut Space is a mentoring program platform built with Django and Wagtail CMS. While it includes a Wagtail-based blog, the primary application is a Django system that manages:

- **Recurring application and ranking processes** for cohort selection
- **Session management** (cohorts/mentoring sessions) with participants, navigators, and captains
- **Application workflows** including surveys, review, scoring, and team formation
- **Team formation and management** with availability matching and project assignments
- **Email notifications** throughout the application and acceptance process

**Important:** This is NOT primarily a meetup site - that was the original vision but is no longer accurate. The focus is on managing cohort-based mentoring programs.

## Project Structure

```
wagtail-indymeet/
├── accounts/          # User authentication and profiles (CustomUser model)
├── home/              # Main Django app + Wagtail pages
│   ├── models/
│   │   ├── session.py     # Session and SessionMembership models
│   │   ├── event.py       # Event models
│   │   └── resource.py    # Resource models
│   │   └── talk.py        # Talk w/ GIS PointField
│   ├── serializers/
│   │   └── talks.py       # GeoJSON REST API serializer
│   ├── views/
│   │   └── talks.py       # TemplateView + ListAPIView
│   ├── templates/
│   │   └── home/talks/    # Importmap for Three.js
│   ├── management/
│   │   └── commands/      # Django management commands
│   └── puput_migrations/  # Blog-specific migrations
├── indymeet/          # Django project settings
│   ├── settings/
│   │   ├── base.py       # Shared settings
│   │   ├── dev.py        # Local development
│   │   ├── test.py       # Test settings
│   │   └── production.py # Production settings
│   └── templates/
├── theme/             # Tailwind CSS theme app
├── docs/              # Project documentation (currently sparse)
├── tests/             # Project-level tests
└── scripts/           # Utility scripts (e.g., local.sh)
```

## Technology Stack

- **Backend:** Django 5.2, Wagtail CMS, PostgreSQL + PostGIS (GIS extension), Django REST Framework + GeoJSON APIs
- **Frontend:** Tailwind CSS, Alpine.js, Three.js (3D globe), Leaflet.js (admin geo-widget)
- **Package Management:** uv (fast Python package installer)
- **Deployment:** Dokku (Heroku buildpacks)
- **Testing:** pytest, pytest-django, playwright
- **Email:** django-anymail
- **Blog:** Puput (integrated with Wagtail)

## Development Workflow

### Setup Commands
```bash
# Start all services (Django, DB, etc.)
just up

# In a new terminal, run setup commands
just migrate
just superuser

# Tailwind setup (if needed)
just tailwind-install
```

### Testing Commands
```bash
just test                   # All tests except Playwright
just test-fast              # All tests, reusing the database
just test-playwright        # Playwright tests
just test-playwright-headed # Playwright tests with visible browser
```

### Running Commands
- **Always prefer `just` recipes** (`just test`, `just migrate`, `just makemigrations`, `just manage <args>`, etc.) over calling `python manage.py`, `pytest`, or `uv run` directly on the host.
- The host Python environment cannot build GDAL/GeoDjango's native extensions, so anything invoking Django settings (tests, migrations, shell, management commands) fails outside Docker. `just` recipes run these inside the `django` container where the dependencies are installed.
- If a command has no matching `just` recipe, run it via `docker compose exec django uv run python manage.py <command>` instead of running it on the host.

### Common Tasks
- **Adding Django functionality** (most common contributor task)
- **Creating Wagtail page models and StreamField blocks** (currently limited, needs improvement)
- **Writing tests** (both standard pytest and Playwright for UI)
- **Frontend work** with Tailwind CSS

## Coding Standards

### General Guidelines
- **Use type hints** for all function signatures
- Follow pre-commit hooks configuration (includes flake8, etc.)
- Write tests alongside all new features
- Generate high-level architecture/design documentation in `docs/` folder
- Write helpful docstrings that provide context
- Avoid obvious or redundant inline comments for code.
- Run zizmor security checks on GitHub Actions workflows when modifying `.github/` directory

### GitHub Actions Security
- **Run zizmor locally** when modifying workflow files: `just zizmor`
- Zizmor checks for security issues in GitHub Actions workflows
- The zizmor workflow runs automatically on PRs that modify `.github/` directory
- Address any security findings before committing workflow changes

### Testing Requirements
- **Always run tests** before considering work complete
- Write unit tests for new functionality (pytest or Django TestCase)
- For JavaScript/frontend interactions, use Playwright tests with `@pytest.mark.playwright`
- Playwright tests run with: `just test-playwright`
- Playwright tests should avoid generic wait calls

### Type Annotations Example
```python
from typing import Optional
from django.http import HttpRequest, HttpResponse


def process_application(
    request: HttpRequest, session_id: int, user_id: Optional[int] = None
) -> HttpResponse:
    """Process an application submission for a session."""
    ...
```

## Architecture Notes

### Key Models
- **`CustomUser`** (accounts.CustomUser): AUTH_USER_MODEL, extends Django's User
- **`Session`**: Represents a mentoring cohort with dates, applications, and participants
- **`SessionMembership`**: Through model connecting users to sessions with roles
- **Survey/Question/UserSurveyResponse**: Application and survey system
- **Event**: Calendar events (legacy from original meetup vision)

### Settings Configuration
- Multiple settings files: `base.py`, `dev.py`, `test.py`, `production.py`
- Uses `python-dotenv` for environment variables
- Database via `dj-database-url`
- Wagtail customizations for blog integration

### Authentication & Profiles
- Custom user model: `accounts.CustomUser`
- Profile model: `accounts.UserProfile`
- Email confirmation workflow
- Role-based memberships (Captain, Navigator, Djangonaut)

## Deployment

### Platform
- **Dokku** with Heroku buildpacks
- **Important quirk:** Tailwind/npm packages must be copied to root directory for buildpacks, which confuses Dependabot

### Environments
- **Production:** https://djangonaut.space (deploys from `main` branch)
- **Staging:** https://staging.djangonaut.space/ (deploys from `develop` branch)

### Deployment Workflow
1. Create PR from `develop` to `main` for production releases
2. Merge using merge commit (not squash)
3. `main` requires linear history
4. If committing directly to `main`, rebase `develop` on `main` afterward

## Important Considerations

### When Writing Code
- **Focus on Django application features** - most contributions will be here
- **Wagtail blocks need improvement** - the current StreamField blocks are limited
- **Documentation is sparse** - please generate architecture docs in `docs/` when adding major features
- **Testing is mandatory** - no exceptions
- **Avoid local imports** - When possible, put the imports at the top of the file

### Database Patterns
- Use Django ORM best practices
- Leverage custom QuerySets (see `home.managers`)
- Be mindful of N+1 queries in admin and views
- Use `select_related` and `prefetch_related` appropriately

### Wagtail Patterns
- Puput blog is integrated via custom migration module
- Custom image app config: `home.apps.CustomImagesAppConfig`
- StreamField blocks should be reusable and well-documented

### Frontend Patterns
- Tailwind classes for styling
- Alpine.js for interactivity
- Forms use `widget_tweaks` for template-level customization
- Custom form renderer: `indymeet.settings.FormRenderer`

## Documentation Standards

When adding significant features or changes:

1. **Update or create docs in `docs/` folder:**
   - Architecture decisions
   - Data model diagrams
   - Workflow explanations
   - Integration guides

2. **Write clear docstrings:**
   - Explain "why" not just "what"
   - Include usage examples for complex functions
   - Document parameters and return types

3. **Update README.md** if:
   - Setup process changes
   - New environment variables added
   - New dependencies required

## Environment Variables

Key variables (see `.env.template` files):
- `SECRET_KEY`: Django secret key
- `DATABASE_URL`: PostgreSQL connection string
- `ENABLE_TOOLBAR`: Enable Django Debug Toolbar
- Email configuration for django-anymail
- Sentry DSN for error tracking
- reCAPTCHA keys

## Git Workflow

- **Main branch:** `main` (production)
- **Development branch:** `develop` (staging)
- **Feature branches:** `feature/AmazingFeature`
- Use pre-commit hooks: `uv run pre-commit install`
- Rebase feature branches on `develop` before merging
- Linear history required on `main`

## Common Commands Reference

```bash
# Services
just up                          # Start all services
just up-detached                 # Start all services in the background
just down                        # Stop all services
just logs                        # Follow Django logs

# Dependency management
just add package-name            # Add main dependency
just add-dev package-name        # Add dev dependency
just add-test package-name       # Add test dependency
just upgrade                     # Update all dependencies
just upgrade-package name        # Update specific package

# Database
just migrate
just makemigrations
just dbshell

# Fixtures
just dumpdata
just loaddata

# Testing
just test                        # All tests except Playwright
just test-fast                   # All tests, reusing the database
just test path/to/test.py        # Specific test file
just test-playwright             # Playwright tests only
just test-playwright-headed      # Playwright tests with visible browser

# Tailwind
just tailwind-install
just tailwind-start
just tailwind-build              # Production build

# GitHub Actions Security
just zizmor                      # Check all workflows
```

## Resources

- **Repository:** https://github.com/djangonaut-space/wagtail-indymeet
- **Production Site:** https://djangonaut.space
- **Staging Site:** https://staging.djangonaut.space/
- **Django Docs:** https://docs.djangoproject.com/
- **Wagtail Docs:** https://docs.wagtail.org/
- **uv Docs:** https://docs.astral.sh/uv/

---

**Remember:** Always run tests, write documentation, use type hints, and focus on building features for the Django application that supports the Djangonaut Space mentoring program.
- Don't import modules in the method if it's not needed
