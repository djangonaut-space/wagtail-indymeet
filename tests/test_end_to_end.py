import os
from logging import getLogger

import pytest
from playwright.sync_api import expect
from playwright.sync_api import Page

logger = getLogger(__name__)

# Mark all tests as playwright
pytestmark = pytest.mark.playwright


@pytest.fixture
def playwright_credentials():
    try:
        username = os.environ["PLAYWRIGHT_TEST_USERNAME"]
    except KeyError as e:
        raise KeyError(
            "Set PLAYWRIGHT_TEST_USERNAME environment variable "
            "(.env file) to the username for the playwright_test user. You "
            "may need run `python manage.py create_playwright_user`"
        ) from e
    try:
        password = os.environ["PLAYWRIGHT_TEST_PASSWORD"]
    except KeyError as e:
        raise KeyError(
            "Set PLAYWRIGHT_TEST_PASSWORD environment variable "
            "(.env file) to the password for the playwright_test user. You "
            "may need to run `python manage.py create_playwright_user`"
        ) from e
    return username, password


@pytest.fixture
def page(page: Page, base_url: str):
    # Redefine the page to force it to start at the base url
    page.goto(base_url)
    yield page


def test_smoketest(page: Page):
    """
    Confirm the application is up and able to access the database.
    """
    expect(
        page.get_by_role("heading", name="Where contributors launch")
    ).to_be_visible()
    page.get_by_role("link", name="Sessions").click()
    page.get_by_role("heading", name="Sessions")
    page.get_by_role("link", name="Events").click()
    page.get_by_role("heading", name="Events")


class TestWagtailAdmin:
    @pytest.fixture
    def page(self, page: Page, playwright_credentials):
        """Log in as the staff playwright test user"""
        page.goto("/admin/login/?next=/admin/")
        username, password = playwright_credentials
        page.get_by_placeholder("Enter your username").fill(username)
        page.get_by_placeholder("Enter password").fill(password)
        page.get_by_role("button", name="Sign in").click()
        yield page
        self.clean_up(page)

    def clean_up(self, page: Page):
        """Delete any created data"""
        page.goto("/admin/")
        # Delete the test blog
        page.get_by_role("button", name="Pages").click()
        page.get_by_role("link", name="Pages created in indymeet").click()
        page.get_by_role("link", name="Playwright Test", exact=True).click()
        page.get_by_role("button", name="Actions").click()
        page.get_by_label("Delete page 'Playwright Test'").click()
        page.get_by_role("button", name="Yes, delete it").click()
        expect(
            page.get_by_role("link", name="Playwright Test", exact=True)
        ).not_to_be_visible()

    def test_wagtail_admin(self, page: Page):
        # Create test blog
        page.get_by_role("button", name="Pages").click()
        page.get_by_role("link", name="Pages created in indymeet").click()
        page.get_by_role("button", name="Actions").click()
        page.get_by_role("link", name="Add child page").click()
        page.get_by_role("link", name=" Blog").click()
        page.get_by_role("textbox", name="Description").click()
        page.get_by_role("textbox", name="Description").fill("Playwright Test")
        page.get_by_placeholder("Page title*").click()
        page.get_by_placeholder("Page title*").fill("Playwright Test")
        page.get_by_role("button", name="Save draft").click()
        page.get_by_role("link", name="Playwright Test", exact=True).click()
        expect(
            page.get_by_role("link", name="Playwright Test", exact=True)
        ).to_be_visible()
