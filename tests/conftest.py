import os

import pytest
from playwright.sync_api import expect

expect.set_options(timeout=5_000)


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--pause-at-end",
        action="store_true",
        default=False,
        help="Pause at the end of Playwright tests for manual exploration",
    )


@pytest.fixture
def pause_at_end(request):
    """Fixture to check if --pause-at-end flag was provided. Only works with --headed"""
    pause = request.config.getoption("--pause-at-end")
    headed = request.config.getoption("--headed")
    return pause and headed


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
