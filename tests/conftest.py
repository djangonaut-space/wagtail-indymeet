import os
import re

import pytest
from playwright.sync_api import Page, expect

expect.set_options(timeout=5_000)


def drag_select(page: Page, from_locator, to_locator) -> None:
    """Simulate a mouse drag selection between two elements.

    Uses explicit mouse events (mousedown/mousemove/mouseup) instead of
    Playwright's drag_to(), which uses HTML5 drag events that libraries
    like Viselect don't listen for — causing failures in WebKit.
    """
    from_locator.scroll_into_view_if_needed()
    to_locator.scroll_into_view_if_needed()
    box_start = from_locator.bounding_box()
    box_end = to_locator.bounding_box()
    start_x = box_start["x"] + box_start["width"] / 2
    start_y = box_start["y"]
    end_x = box_end["x"] + box_end["width"] / 2
    end_y = box_end["y"] + box_end["height"]
    page.mouse.move(start_x, start_y)
    page.mouse.down()
    page.mouse.move(end_x, end_y)
    # Wait for viselect to visually mark the last cell before releasing
    expect(to_locator).to_have_class(re.compile(r"\bselecting\b"))
    page.mouse.up()


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
