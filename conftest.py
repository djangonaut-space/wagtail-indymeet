import pytest

BD_SETTINGS = {"BUTTONDOWN_API_KEY": "test-api-key"}


@pytest.fixture(autouse=True)
def disable_zoom_credentials(settings):
    """Clear Zoom credentials for every test so no test accidentally hits the real API.

    Tests that need Zoom enabled must opt in with @override_settings(ZOOM_ACCOUNT_ID=...).
    """
    settings.ZOOM_ACCOUNT_ID = ""
    settings.ZOOM_CLIENT_ID = ""
    settings.ZOOM_CLIENT_SECRET = ""


@pytest.fixture(autouse=True)
def use_immediate_task_backend(settings):
    """Force the immediate task backend for all tests.

    The Docker environment may set TASK_BACKEND to the database backend, but tests
    need tasks to execute synchronously so assertions can observe the results directly.
    """
    settings.TASKS = {
        "default": {
            "BACKEND": "django_tasks.backends.immediate.ImmediateBackend",
        }
    }
