import os

from playwright.sync_api import expect

expect.set_options(timeout=5_000)


def pytest_runtest_setup(item):
    """
    Configure pytest environment per test item
    """
    # Was pytest run with -m playwright
    running_playwright = "playwright" in item.config.option.markexpr.split()
    # Does the test have @pytest.mark.playwright
    test_is_playwright = bool(list(item.iter_markers(name="playwright")))
    if running_playwright and test_is_playwright:
        # We can only manipulate the environment once, so we should only
        # do this if we know we're only running playwright tests.
        os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
