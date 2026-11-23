"""Signal handlers for the home app."""

from django.apps import AppConfig, apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.db import DEFAULT_DB_ALIAS, connections
from django.db.migrations.executor import MigrationExecutor
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from wagtail.coreutils import get_supported_content_language_variant
from wagtail.models import Collection, Locale, Page, Site

from home.models import HomePage

# Title of the page wagtail/migrations/0002_initial_data.py creates.
WAGTAIL_PLACEHOLDER_TITLE = "Welcome to your new Wagtail site!"


def is_fully_migrated(using: str) -> bool:
    executor = MigrationExecutor(connections[using])
    return not executor.migration_plan(executor.loader.graph.leaf_nodes())


# post_migrate is sent once per app; listening for this one runs it once.
@receiver(
    post_migrate,
    sender=apps.get_app_config("home"),
    dispatch_uid="home.ensure_site_structure",
)
def ensure_site_structure(
    sender: AppConfig, using: str = DEFAULT_DB_ALIAS, **kwargs
) -> None:
    """Create the Locale, root Page and Collection, HomePage and Site if missing.

    The site needs these to serve pages. Wagtail's migrations create all but
    the HomePage, which replaces Wagtail's placeholder welcome page. The
    ``flush`` command deletes all of them, and TransactionTestCase and
    pytest-django's live_server flush after every test. Django sends
    post_migrate after both ``migrate`` and ``flush``, so creating anything
    missing then sets up new databases and keeps the site, and the tests that
    follow, working after a flush. Wagtail's default Editors and Moderators
    groups and moderation workflow are not recreated after a flush.

    ``migrate`` passes a plan and may have stopped at, or rolled back to, an
    earlier migration where these tables don't match the models yet, so only
    run once every migration is applied. ``flush`` passes no plan and only
    runs against a migrated database.
    """
    if "plan" in kwargs and not is_fully_migrated(using):
        return
    Locale.objects.get_or_create(
        language_code=get_supported_content_language_variant(settings.LANGUAGE_CODE)
    )
    if Collection.get_first_root_node() is None:
        Collection.add_root(name="Root")
    root = Page.get_first_root_node() or Page.add_root(title="Root", slug="root")
    if HomePage.objects.exists():
        if not Site.objects.exists():
            Site.objects.create(
                hostname="localhost",
                root_page=HomePage.objects.first(),
                is_default_site=True,
            )
        return
    # Wagtail's migrations create a placeholder welcome page. Only delete a
    # page that still matches it exactly and has no children, so a page
    # someone created or edited is never removed. Deleting it also deletes
    # the Site pointing at it.
    Page.objects.filter(
        depth=2,
        slug="home",
        title=WAGTAIL_PLACEHOLDER_TITLE,
        numchild=0,
        content_type=ContentType.objects.get_for_model(Page),
    ).delete()
    home = root.add_child(instance=HomePage(title="Home", slug="home"))
    Site.objects.update_or_create(
        is_default_site=True,
        defaults={"hostname": "localhost", "root_page": home},
    )
