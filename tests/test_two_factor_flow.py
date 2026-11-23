"""
Browser test for two-factor authentication.

Kept to a single test because each Playwright test is slow (see the note at the
top of ``tests/test_end_to_end.py``).
"""

from base64 import b32decode

import pytest
from django.urls import reverse
from django_otp.oath import totp
from playwright.sync_api import BrowserContext
from playwright.sync_api import expect
from playwright.sync_api import Page

from accounts.models import CustomUser

PASSWORD = "testpass123"


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
    user = CustomUser.objects.create_user(
        username="twofactortest",
        email="twofactortest@example.com",
        password=PASSWORD,
    )
    user.profile.email_confirmed = True
    user.profile.save()
    return user


def submit_password(page: Page, user: CustomUser) -> None:
    page.goto(reverse("login"))
    page.get_by_label("Username").fill(user.username)
    page.get_by_label("Password").fill(PASSWORD)
    page.get_by_role("button", name="Login").click()


def submit_code(page: Page, code: str) -> None:
    page.get_by_label("Authentication code").fill(code)
    page.get_by_role("button", name="Verify").click()


@pytest.mark.playwright
def test_enrol_then_log_in_with_authenticator_and_recovery_code(
    page: Page, user: CustomUser
):
    profile_url = f"**{reverse('profile')}"
    verify_url = f"**{reverse('two_factor_verify')}"

    # Enrol an authenticator app from the profile page.
    submit_password(page, user)
    page.wait_for_url(profile_url)
    page.get_by_role("link", name="Manage two-factor authentication").click()
    page.get_by_role("link", name="Set up two-factor authentication").click()
    expect(page.get_by_alt_text("QR code for setting up")).to_be_visible()
    key = b32decode(page.get_by_test_id("manual-entry-key").inner_text())

    page.get_by_label("6-digit code").fill(f"{totp(key):06d}")
    page.get_by_label("Current password").fill(PASSWORD)
    page.get_by_role("button", name="Turn on two-factor authentication").click()

    expect(page.get_by_role("heading", name="Save your recovery codes")).to_be_visible()
    recovery_codes = (
        page.get_by_test_id("recovery-codes").locator("li").all_inner_texts()
    )
    assert len(recovery_codes) == 10
    page.get_by_role("link", name="I've saved my codes").click()
    expect(page.get_by_text("Two-factor authentication is on")).to_be_visible()

    # Logging in now needs a code. A recovery code works, and says how many
    # are left.
    page.context.clear_cookies()
    submit_password(page, user)
    page.wait_for_url(verify_url)
    submit_code(page, recovery_codes[0])
    page.wait_for_url(profile_url)
    expect(page.get_by_text("You have 9 recovery codes left.")).to_be_visible()

    # A wrong code is refused and the user stays on the code step.
    page.context.clear_cookies()
    submit_password(page, user)
    page.wait_for_url(verify_url)
    submit_code(page, "not-a-code")
    expect(page.get_by_text("That code is not valid.")).to_be_visible()

    # The authenticator app works. The code used during setup can't be
    # replayed, so use the one for the next 30-second window, which the server
    # accepts to allow for clock drift.
    submit_code(page, f"{totp(key, drift=1):06d}")
    page.wait_for_url(profile_url)
    expect(page.get_by_text("Two-factor authentication: On")).to_be_visible()
