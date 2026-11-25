"""
Browser test for two-factor authentication.

Kept to a single test because each Playwright test is slow (see the note at the
top of ``tests/test_end_to_end.py``).
"""

import pytest
from django.urls import reverse
from playwright.sync_api import BrowserContext
from playwright.sync_api import expect
from playwright.sync_api import Page

from accounts.models import CustomUser
from accounts.tests.two_factor_helpers import create_user
from accounts.tests.two_factor_helpers import current_code
from accounts.tests.two_factor_helpers import PASSWORD


@pytest.fixture
def context(new_context, live_server) -> BrowserContext:
    """Open the browser context against the live server's database."""
    return new_context(base_url=live_server.url)


@pytest.fixture
def page(context: BrowserContext):
    page = context.new_page()
    yield page
    page.close()
    context.close()


@pytest.fixture
def user(db) -> CustomUser:
    return create_user("twofactortest")


def submit_password(page: Page, user: CustomUser) -> None:
    page.goto(reverse("login"))
    page.get_by_label("Username").fill(user.username)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Login").click()


def submit_code(page: Page, code: str) -> None:
    page.get_by_label("Code").fill(code)
    page.get_by_role("button", name="Sign In").click()


@pytest.mark.playwright
def test_enrol_then_log_in_with_authenticator_and_recovery_code(
    page: Page, user: CustomUser
):
    profile_url = f"**{reverse('profile')}"
    code_url = f"**{reverse('mfa_authenticate')}"

    # Enrol an authenticator app from the profile page, confirming the
    # password on the way.
    submit_password(page, user)
    page.wait_for_url(profile_url)
    page.get_by_role("link", name="Manage two-factor authentication").click()
    page.get_by_role("link", name="Activate").click()
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Confirm").click()

    expect(page.locator("img[src^='data:image/svg+xml']")).to_be_visible()
    secret = page.get_by_label("Authenticator secret").input_value()
    page.get_by_label("Authenticator code").fill(current_code(secret))
    page.get_by_role("button", name="Activate").click()

    expect(page.get_by_role("heading", name="Recovery Codes")).to_be_visible()
    recovery_codes = page.get_by_label("Unused codes").input_value().split()
    assert len(recovery_codes) == 10

    # Logging in now needs a code, and a recovery code works.
    page.context.clear_cookies()
    submit_password(page, user)
    page.wait_for_url(code_url)
    submit_code(page, recovery_codes[0])
    page.wait_for_url(profile_url)

    # A wrong code is refused and the user stays on the code step, where the
    # authenticator app's code then lets them in.
    page.context.clear_cookies()
    submit_password(page, user)
    page.wait_for_url(code_url)
    submit_code(page, "000000")
    expect(page.get_by_text("Incorrect code.")).to_be_visible()

    submit_code(page, current_code(secret))
    page.wait_for_url(profile_url)
    expect(page.get_by_text("Two-factor authentication: On")).to_be_visible()
