import pytest


@pytest.fixture(autouse=True)
def disable_zoom_credentials(settings):
    """Clear Zoom credentials for every test so no test accidentally hits the real API.

    Tests that need Zoom enabled must opt in with @override_settings(ZOOM_ACCOUNT_ID=...).
    """
    settings.ZOOM_ACCOUNT_ID = ""
    settings.ZOOM_CLIENT_ID = ""
    settings.ZOOM_CLIENT_SECRET = ""
