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

- **Backend:** Django 5.2, Wagtail CMS, PostgreSQL
- **Frontend:** Tailwind CSS, Alpine.js
- **Package Management:** uv (fast Python package installer)
- **Deployment:** Dokku (Heroku buildpacks)
- **Testing:** pytest, pytest-django, playwright
- **Email:** django-anymail
- **Blog:** Puput (integrated with Wagtail)

## Development Workflow

### Setup Commands
```bash
# Install dependencies (creates venv automatically)
uv sync --extra dev --extra test

# Database setup
uv run python manage.py migrate
uv run python manage.py createsuperuser

# Tailwind setup
uv run python manage.py tailwind install

# Run development servers
uv run python manage.py runserver        # Django server
uv run python manage.py tailwind start   # Tailwind watcher (separate terminal)

# Or use the convenience script (non-Windows)
./scripts/local.sh
```

### Testing Commands
```bash
# Run standard tests
uv run pytest

# Run Playwright tests (browser-based)
uv run playwright install --with-deps
uv run pytest -m playwright
uv run pytest -m playwright --headed  # See browser
```

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

### Testing Requirements
- **Always run tests** before considering work complete
- Write unit tests for new functionality (pytest or Django TestCase)
- For JavaScript/frontend interactions, use Playwright tests with `@pytest.mark.playwright`
- Playwright tests run with: `uv run pytest -m playwright`

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

## Upcoming Major Feature: Application Administration System

The next major development effort involves building a comprehensive application review and team formation system. This is documented here for context when working on related features.

### Phase 1: Application Administration
- Copy surveys/applications from previous sessions
- Manage application questions and structure

### Phase 2: Applying (Issue #303)
- View other application responses
- Copy responses from previous applications
- Edit application responses
- Upload availability schedules
- Email notifications on submission

### Phase 3: Application Review
- View all questions for a survey
- View all responses for a specific question
- Score responses (-1, 0, 1)
- View applicant's responses to other questions
- Analyze tutorial submissions for code quality
- **Alternative:** CSV export/import to integrate with existing process

### Phase 4: Team Formation
- **Availability overlap analysis:** Count overlapping times for navigators
- **Advanced filtering:**
  - Score, project selections, tutorial quality
  - Diversity metrics, gender diversity
  - Selection rank, team assignments
  - Availability overlap counts
  - Previous application history and scores
- **Interactive team building:**
  - Select people and associate with rank
  - Find overlapping times for navigator + multiple people
  - Find overlapping times for captain + person
  - Form teams (navigator, captain, djangonauts) with validation

### Phase 5: Teams Creation
- Models for teams attached to sessions:
  - Team drive link, multiple captains/navigators
  - Project name/link, resource links
- Update Session model for notification tracking
- Update SessionMembership for acceptance workflow
- Admin actions:
  - Send acceptance emails (with confirmation)
  - Send reminder emails about accepting
- Acceptance workflow:
  - Create membership acceptance page
  - Send notification about next steps
- Welcome email admin action for all teams
- Team views:
  - Organizers/navigators/captains view survey responses
  - Navigators/captains update project info and resources
  - Team members view project links, contacts, drive folder
- Generate Google Sheets for contacts

### Phase 6: Team Formation Algorithm
**Proposed algorithm for optimal team assignments:**

1. Sort members by: ascending rank → ascending availability → descending score
2. Allocate members to navigators where 5+ hours overlap
3. Maximize full teams before moving to next navigator
4. **Tree-based optimization:**
   - Root node = session
   - Child nodes = adding next available person to teams
   - Only add if availability check passes for that team
   - Per-team tracking
5. **Evaluation:** Sort by longest branches to identify best team configurations

## Important Considerations

### When Writing Code
- **Focus on Django application features** - most contributions will be here
- **Wagtail blocks need improvement** - the current StreamField blocks are limited
- **Documentation is sparse** - please generate architecture docs in `docs/` when adding major features
- **Testing is mandatory** - no exceptions

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
- Custom form renderer: `indymeet.settings.base.FormRenderer`

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
# Dependency management
uv add package-name              # Add main dependency
uv add --dev package-name        # Add dev dependency
uv add --optional test package   # Add test dependency
uv lock --upgrade                # Update all dependencies
uv lock --upgrade-package name   # Update specific package

# Database
uv run python manage.py migrate
uv run python manage.py makemigrations
uv run python manage.py dbshell

# Fixtures
uv run python manage.py dumpdata [options] -o fixtures/data.json
uv run python manage.py loaddata fixtures/data.json

# Testing
uv run pytest                    # All tests except playwright
uv run pytest -m playwright      # Playwright tests only
uv run pytest --reuse-db         # Reuse database
uv run pytest path/to/test.py    # Specific test file

# Tailwind
uv run python manage.py tailwind install
uv run python manage.py tailwind start
uv run python manage.py tailwind build   # Production build

# Production/staging locally
uv run python manage.py runserver --settings=indymeet.settings.production
uv run python manage.py migrate --settings=indymeet.settings.production
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
