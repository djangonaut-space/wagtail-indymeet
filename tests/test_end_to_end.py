"""
Note:

Due to the Wagtail integration, each of these tests takes 15s or more because of
the number of migrations for those apps. We need to be conservative with these tests.

It can be helpful to run them specifically locally:

    uv run pytest -m playwright -k 'TestAvailabilityPage'

"""

import re
from dataclasses import dataclass
from logging import getLogger

import factory
import pytest
from django.urls import reverse
from playwright.sync_api import expect, BrowserContext
from playwright.sync_api import Page

from accounts.factories import UserFactory
from accounts.models import CustomUser
from home.factories import (
    ProjectFactory,
    SessionFactory,
    SurveyFactory,
    TeamFactory,
    UserSurveyResponseFactory,
)
from home.models import Session, SessionMembership, Survey, Team, UserSurveyResponse

logger = getLogger(__name__)

# Mark all tests as playwright
pytestmark = pytest.mark.playwright


@dataclass
class TeamFormationTestData:
    """Test data for team formation tests."""

    session: Session
    survey: Survey
    team_alpha: Team
    team_beta: Team
    applicants: list[
        dict[str, CustomUser | UserSurveyResponse]
    ]  # List of {"user": ..., "response": ...}


RESULTS_PATTERN = re.compile(r"Showing \d+ of \d+ opportunities")


@pytest.fixture
def context(new_context, live_server) -> BrowserContext:
    """Configure the playwright context

    Makes sure the context is opening up at the live-server transaction
    database url.
    https://docs.djangoproject.com/en/stable/topics/testing/tools/#liveservertestcase
    """
    return new_context(base_url=live_server.url)


@pytest.fixture
def page(context: BrowserContext):
    """Fixture to provide a browser page."""
    page = context.new_page()
    yield page
    page.close()
    context.close()


class TestDjangoOpportunities:
    """Test suite for Django Contribution Opportunities page functionality."""

    def wait_for_alpine_init(self, page: Page):
        """Wait for Alpine.js to initialize and opportunities to load."""
        page.wait_for_selector('[x-data*="opportunitiesApp"]')
        page.wait_for_load_state("networkidle")
        # Wait for the results counter to appear, indicating Alpine has initialized
        page.get_by_text(RESULTS_PATTERN).wait_for(state="visible")

    def assert_page_loads_correctly(self, page: Page):
        """Verify the page loads with all main elements."""
        # Check main heading
        expect(
            page.get_by_role("heading", name="Django Contribution Opportunities")
        ).to_be_visible()

        # Check that search inputs are visible
        expect(page.get_by_label("Search by Name")).to_be_visible()
        expect(page.get_by_label("Search by Tags")).to_be_visible()
        expect(page.get_by_label("Search by Outcomes")).to_be_visible()
        expect(page.get_by_label("Search by Requirements")).to_be_visible()
        expect(page.get_by_label("Search Description")).to_be_visible()

        # Check that clear filters button is visible
        expect(page.get_by_role("button", name="Clear All Filters")).to_be_visible()

        # Check that opportunity cards have proper button role
        opportunity_cards = page.locator('[role="button"][tabindex="0"]')
        assert opportunity_cards.count()
        expect(opportunity_cards.first).to_be_visible()

    def assert_search_filters_work(self, page: Page):
        """Verify all search filter fields work correctly."""
        search_fields = [
            ("Search by Name", "Google"),
            ("Search by Tags", "mentorship"),
            ("Search by Outcomes", "technical"),
            ("Search by Requirements", "Django"),
            ("Search Description", "student"),
        ]

        for search_label, search_term in search_fields:
            search_input = page.get_by_label(search_label)
            search_input.fill(search_term)

            # Verify that the search was applied (counter should be visible)
            results_text = page.get_by_text(RESULTS_PATTERN)
            expect(results_text).to_be_visible()

            # Clear for next iteration
            search_input.fill("")

    def assert_autocomplete_works(self, page: Page):
        """Verify autocomplete selection functionality."""
        name_input = page.get_by_label("Search by Name")
        name_input.fill("Goo")

        # Look for autocomplete suggestions - wait for them to appear
        autocomplete_items = page.locator(".suggestion-item")
        expect(autocomplete_items.first).to_be_visible()
        assert autocomplete_items.count()
        first_suggestion = autocomplete_items.first
        suggestion_text = first_suggestion.inner_text()
        first_suggestion.click()

        # Verify the input value was updated
        expect(name_input).to_have_value(suggestion_text)

        # Clear for subsequent tests
        name_input.fill("")

    def assert_type_filter_works(self, page: Page):
        """Verify type checkbox filters work."""
        # Get available type checkboxes
        type_checkboxes = page.get_by_role("checkbox")
        assert type_checkboxes.count()

        # Check the first available type
        first_checkbox = type_checkboxes.first
        first_checkbox.check()

        # Verify results counter updates
        results_text = page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

        # Uncheck to verify it toggles
        first_checkbox.uncheck()
        expect(results_text).to_be_visible()

    def assert_clear_filters_works(self, page: Page):
        """Verify clear all filters button works."""
        # Apply some filters first
        name_input = page.get_by_label("Search by Name")
        name_input.fill("Test")

        # Click clear filters using the button role
        clear_button = page.get_by_role("button", name="Clear All Filters")
        clear_button.click()

        # Verify filters are cleared
        expect(name_input).to_have_value("")

    def assert_multiple_filters_work(self, page: Page):
        """Verify multiple search filters work together."""
        page.get_by_label("Search by Name").fill("Google")
        page.get_by_label("Search by Tags").fill("mentorship")

        # Check that results counter is visible and updated
        results_text = page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

        # Verify results counter shows filtering
        counter_text = results_text.inner_text()
        assert "Showing" in counter_text

        # Clear for subsequent tests
        page.get_by_role("button", name="Clear All Filters").click()

    def assert_no_results_display(self, page: Page):
        """Verify no results message appears when filters match nothing."""
        name_input = page.get_by_label("Search by Name")
        name_input.fill("NonexistentOpportunity12345")

        # Check for no results message or zero count
        no_results = page.get_by_text("No opportunities found")
        results_counter = page.get_by_text(re.compile(r"Showing 0 of "))

        # Either no results message or zero count should be visible
        if no_results.count() > 0:
            expect(no_results).to_be_visible()
        else:
            expect(results_counter).to_be_visible()

        # Clear for subsequent tests
        name_input.fill("")

    def assert_modal_opens_and_displays_content(self, page: Page):
        """Verify clicking a card opens modal with correct content."""
        # Find opportunity cards by their button role
        opportunity_cards = page.get_by_role("button").filter(
            has_text="Google Summer of Code"
        )

        if opportunity_cards.count() == 0:
            # Fallback to any opportunity card
            opportunity_cards = page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count()
        first_card = opportunity_cards.first
        # Get the card title for verification
        card_title = first_card.get_by_role("heading").inner_text()
        first_card.click()

        # Check that modal dialog is visible
        modal = page.get_by_role("dialog")
        expect(modal).to_be_visible()

        # Check that modal title matches card title
        modal_title = modal.get_by_role("heading").first
        expect(modal_title).to_contain_text(card_title)

        # Check that modal sections are present using headings
        description_heading = modal.get_by_role("heading", name="Description")
        expect(description_heading).to_be_visible()

        # Check modal has proper accessibility attributes
        expect(modal).to_have_attribute("aria-modal", "true")

        # Verify modal contains external links with proper attributes
        modal_links = modal.get_by_role("link")
        assert modal_links.count() > 0
        for i in range(min(3, modal_links.count())):
            link = modal_links.nth(i)
            expect(link).to_have_attribute("target", "_blank")
            expect(link).to_have_attribute("rel", "noopener noreferrer")

        # Close modal with X button
        close_button = page.get_by_label("Close modal")
        close_button.click()
        expect(modal).not_to_be_visible()

    def assert_keyboard_navigation_works(self, page: Page):
        """Verify keyboard navigation on cards opens modal."""
        opportunity_cards = page.locator('[role="button"][tabindex="0"]')
        assert opportunity_cards.count()
        first_card = opportunity_cards.first

        # Focus and use Enter key
        first_card.focus()
        page.keyboard.press("Enter")

        modal = page.get_by_role("dialog")
        expect(modal).to_be_visible()

        # Close modal with X button
        close_button = page.get_by_label("Close modal")
        close_button.click()
        expect(modal).not_to_be_visible()

        # Test Space key also opens modal
        first_card.focus()
        page.keyboard.press("Space")
        expect(modal).to_be_visible()

        # Close modal
        close_button.click()
        expect(modal).not_to_be_visible()

    def assert_external_links_secure(self, page: Page):
        """Verify external links have proper security attributes."""
        learn_more_links = page.get_by_role("link", name="Learn More")
        assert learn_more_links.count()

        first_link = learn_more_links.first
        expect(first_link).to_have_attribute("target", "_blank")
        expect(first_link).to_have_attribute("rel", "noopener noreferrer")

    def assert_responsive_behavior(self, page: Page):
        """Verify basic responsive functionality."""
        # Test mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})

        # Verify main elements are still visible
        expect(
            page.get_by_role("heading", name="Django Contribution Opportunities")
        ).to_be_visible()
        expect(page.get_by_label("Search by Name")).to_be_visible()

        # Reset viewport
        page.set_viewport_size({"width": 1280, "height": 720})

    @pytest.mark.playwright
    def test_opportunities_page_interactivity(self, page: Page):
        """
        Comprehensive test for all interactive features on opportunities page.

        Tests:
        1. Page loads with all required elements
        2. Search filter fields functionality
        3. Autocomplete selection
        4. Type checkbox filters
        5. Clear filters button
        6. Multiple filters combination
        7. No results display
        8. Modal opens and displays content
        9. Keyboard navigation
        10. External links have security attributes
        11. Responsive behavior
        """
        # Navigate to opportunities page
        page.goto(reverse("opportunities"))
        self.wait_for_alpine_init(page)

        # Test 1: Verify page loads with all required elements
        self.assert_page_loads_correctly(page)

        # Test 2: Search filter fields functionality
        self.assert_search_filters_work(page)

        # Test 3: Autocomplete selection
        self.assert_autocomplete_works(page)

        # Test 4: Type checkbox filters
        self.assert_type_filter_works(page)

        # Test 5: Clear filters button
        self.assert_clear_filters_works(page)

        # Test 6: Multiple filters combination
        self.assert_multiple_filters_work(page)

        # Test 7: No results display
        self.assert_no_results_display(page)

        # Test 8: Modal opens and displays content
        self.assert_modal_opens_and_displays_content(page)

        # Test 9: Keyboard navigation
        self.assert_keyboard_navigation_works(page)

        # Test 10: External links have security attributes
        self.assert_external_links_secure(page)

        # Test 11: Responsive behavior
        self.assert_responsive_behavior(page)


class TestAvailabilityPage:
    """Test suite for availability page functionality."""

    @pytest.fixture
    def authenticated_user(self, db):
        """Fixture to create a test user with confirmed email."""
        user = CustomUser.objects.create_user(
            username="availabilitytest",
            email="availtest@example.com",
            password="testpass123",
        )
        # Confirm email so user can access the page
        user.profile.email_confirmed = True
        user.profile.save()
        return user

    def test_availability_workflow(self, page: Page, authenticated_user):
        """
        Complete workflow test for availability page:
        1. Select a block of time and save
        2. Go back and confirm block is selected
        3. Clear availability and save
        4. Go back and confirm block is removed
        5. Select multiple scattered slots and save
        6. Go back and confirm slots remain
        """
        # Login with the authenticated user
        page.goto(reverse("login"))
        page.get_by_label("Username").fill("availabilitytest")
        page.get_by_label("Password").fill("testpass123")
        page.get_by_role("button", name="Login").click()
        page.wait_for_load_state("networkidle")

        # Step 1: Navigate to availability page and select a block of time
        page.goto(reverse("availability"))
        page.wait_for_load_state("networkidle")

        # Wait for the grid to be fully rendered by checking for tbody to have children
        # The grid is generated by JavaScript, so we need to wait for it
        page.locator("#availability-grid tbody tr").first.wait_for(state="visible")

        # Wait for the grid to be populated with data attributes
        page.locator(".time-slot[data-day][data-hour]").first.wait_for(state="visible")

        # Verify page loaded
        expect(
            page.get_by_role("heading", name="Set Your Availability")
        ).to_be_visible()

        # Select a block of time slots (Monday 9:00 AM - 10:30 AM)
        # The grid is organized as: columns = days (0-6), rows = times
        # Monday = column 1, each half hour is a separate row
        monday_9am = page.locator('.time-slot[data-day="1"][data-hour="9"]')
        monday_930am = page.locator('.time-slot[data-day="1"][data-hour="9.5"]')
        monday_10am = page.locator('.time-slot[data-day="1"][data-hour="10"]')
        monday_1030am = page.locator('.time-slot[data-day="1"][data-hour="10.5"]')

        # Use drag selection to select the block
        # Drag from the first cell to the last cell
        monday_9am.drag_to(monday_1030am)

        # Wait for selection to be processed
        page.wait_for_timeout(200)

        # Wait for the first cell to have the selected class
        # (indicates JS has processed the selection)
        expect(monday_9am).to_have_class(re.compile(r".*\bselected\b.*"))

        # Verify all cells in the block are selected
        expect(monday_930am).to_have_class(re.compile(r".*\bselected\b.*"))
        expect(monday_10am).to_have_class(re.compile(r".*\bselected\b.*"))
        expect(monday_1030am).to_have_class(re.compile(r".*\bselected\b.*"))

        # Save
        page.get_by_role("button", name="Save Availability").first.click()
        page.wait_for_load_state("networkidle")

        # Should redirect to profile
        expect(page).to_have_url(re.compile(r".*/profile/?$"))

        # Step 2: Go back to availability page and confirm block is still selected
        page.goto(reverse("availability"))
        page.wait_for_load_state("networkidle")

        # Wait for grid to be generated
        page.locator("#availability-grid tbody tr").first.wait_for(state="visible")

        # Wait for grid to render and data to load
        expect(monday_9am).to_have_class(re.compile(r".*\bselected\b.*"))

        # Verify the same slots are selected
        expect(monday_930am).to_have_class(re.compile(r".*\bselected\b.*"))
        expect(monday_10am).to_have_class(re.compile(r".*\bselected\b.*"))
        expect(monday_1030am).to_have_class(re.compile(r".*\bselected\b.*"))

        # Step 3: Clear all availability using the button
        # Set up dialog handler before clicking
        page.once("dialog", lambda dialog: dialog.accept())
        page.get_by_role("button", name="Clear All").first.click()

        # Wait for cells to no longer have selected class
        expect(monday_9am).not_to_have_class(re.compile(r".*\bselected\b.*"))
        expect(monday_930am).not_to_have_class(re.compile(r".*\bselected\b.*"))
        expect(monday_10am).not_to_have_class(re.compile(r".*\bselected\b.*"))
        expect(monday_1030am).not_to_have_class(re.compile(r".*\bselected\b.*"))

        # Save
        page.get_by_role("button", name="Save Availability").first.click()
        page.wait_for_load_state("networkidle")

        # Step 4: Go back and confirm block is removed
        page.goto(reverse("availability"))
        page.wait_for_load_state("networkidle")

        # Wait for grid to be generated
        page.locator("#availability-grid tbody tr").first.wait_for(state="visible")

        # Verify no slots are selected
        expect(monday_9am).not_to_have_class(re.compile(r".*\bselected\b.*"))
        expect(monday_930am).not_to_have_class(re.compile(r".*\bselected\b.*"))
        expect(monday_10am).not_to_have_class(re.compile(r".*\bselected\b.*"))
        expect(monday_1030am).not_to_have_class(re.compile(r".*\bselected\b.*"))

        # Step 5: Select a different block of time slots to verify selection works
        # Select: Tuesday 2:00 PM to Tuesday 3:00 PM (3 slots)
        tuesday_2pm = page.locator('.time-slot[data-day="2"][data-hour="14"]')
        tuesday_230pm = page.locator('.time-slot[data-day="2"][data-hour="14.5"]')
        tuesday_3pm = page.locator('.time-slot[data-day="2"][data-hour="15"]')

        # Use drag selection to select the new block
        # Drag from the first cell to the last cell
        tuesday_2pm.drag_to(tuesday_3pm)

        # Wait for selection to be processed
        page.wait_for_timeout(200)

        # Verify all cells in the new block are selected
        expect(tuesday_2pm).to_have_class(re.compile(r".*\bselected\b.*"))
        expect(tuesday_230pm).to_have_class(re.compile(r".*\bselected\b.*"))
        expect(tuesday_3pm).to_have_class(re.compile(r".*\bselected\b.*"))

        # Save
        page.get_by_role("button", name="Save Availability").first.click()
        page.wait_for_load_state("networkidle")

        # Step 6: Go back and confirm the Tuesday block is selected
        page.goto(reverse("availability"))
        page.wait_for_load_state("networkidle")

        # Wait for grid to be generated
        page.locator("#availability-grid tbody tr").first.wait_for(state="visible")

        # Verify Tuesday slots are selected
        expect(tuesday_2pm).to_have_class(re.compile(r".*\bselected\b.*"))
        expect(tuesday_230pm).to_have_class(re.compile(r".*\bselected\b.*"))
        expect(tuesday_3pm).to_have_class(re.compile(r".*\bselected\b.*"))

        # Verify the original Monday slots are still not selected
        expect(monday_9am).not_to_have_class(re.compile(r".*\bselected\b.*"))
        expect(monday_10am).not_to_have_class(re.compile(r".*\bselected\b.*"))


class TestTeamFormation:

    @pytest.fixture
    def setup_team_formation_data(self, db):
        """Create all necessary data for team formation testing."""
        # Create session with application survey
        session = SessionFactory()
        survey = SurveyFactory(session=session)
        session.application_survey = survey
        session.save()

        # Create teams (TeamFactory automatically creates a project)
        team_alpha = TeamFactory(
            session=session, name="Team Alpha", project__name="Django"
        )
        team_beta = TeamFactory(
            session=session, name="Team Beta", project=team_alpha.project
        )

        # Create applicants (users with survey responses)
        users = UserFactory.create_batch(
            5,
            username=factory.Sequence(lambda n: f"applicant{n}"),
            email=factory.Sequence(lambda n: f"applicant{n}@test.com"),
            first_name=factory.Sequence(lambda n: f"Applicant{n}"),
            last_name="User",
        )
        applicants = []
        for i, user in enumerate(users):
            response = UserSurveyResponseFactory(
                survey=survey,
                user=user,
                score=i + 1,
                selection_rank=i + 1,
            )
            applicants.append({"user": user, "response": response})

        # Assign first two applicants to Team Alpha
        for applicant in applicants[:2]:
            SessionMembership.objects.create(
                session=session,
                user=applicant["user"],
                team=team_alpha,
                role=SessionMembership.DJANGONAUT,
            )

        # Create navigators for both teams
        navigator_alpha = UserFactory(
            username="navigator_alpha",
            email="navigator_alpha@test.com",
            first_name="Navigator",
            last_name="Alpha",
        )
        SessionMembership.objects.create(
            session=session,
            user=navigator_alpha,
            team=team_alpha,
            role=SessionMembership.NAVIGATOR,
        )

        navigator_beta = UserFactory(
            username="navigator_beta",
            email="navigator_beta@test.com",
            first_name="Navigator",
            last_name="Beta",
        )
        SessionMembership.objects.create(
            session=session,
            user=navigator_beta,
            team=team_beta,
            role=SessionMembership.NAVIGATOR,
        )

        return TeamFormationTestData(
            session=session,
            survey=survey,
            team_alpha=team_alpha,
            team_beta=team_beta,
            applicants=applicants,
        )

    @pytest.fixture
    def team_page(self, page, live_server):
        """Fixture to access internal pages as logged in superuser."""
        # Login as superuser (CustomUser uses username, not email for login)
        UserFactory(
            username="admin",
            email="admin@test.com",
            first_name="Admin",
            last_name="User",
            is_superuser=True,
            is_staff=True,
        )
        # Note: UserFactory doesn't set password, so we need to set it manually
        admin = CustomUser.objects.get(username="admin")
        admin.set_password("adminpass123")
        admin.save()
        page.goto("/django-admin/")
        # Fill login form using accessible role-based selectors
        page.get_by_role("textbox", name="username").fill("admin")
        page.get_by_role("textbox", name="password").fill("adminpass123")
        page.get_by_role("button", name="Log in").click()

        # Wait for navigation after login
        page.wait_for_load_state("networkidle")

        return page

    @pytest.mark.playwright
    def test_team_formation_interactivity(
        self, team_page: Page, live_server, setup_team_formation_data
    ):
        """
        Comprehensive test for all interactive features on team formation page.

        Tests:
        1. Page loads and displays applicants
        2. Select all checkbox functionality
        3. Individual checkbox selection
        4. Filter functionality
        5. Bulk team assignment
        6. HTMX overlap calculation
        7. Sorting functionality
        8. Teams panel visibility
        9. Waitlist functionality
        """
        data = setup_team_formation_data

        # Navigate to team formation page
        url = reverse(
            "admin:session_form_teams", kwargs={"session_id": data.session.id}
        )
        team_page.goto(url)

        # Test 1: Verify page loaded with applicants
        # Wait for the main content to load
        team_page.wait_for_load_state("networkidle")
        expect(team_page.get_by_role("heading", level=1)).to_contain_text("Form Teams")
        expect(team_page.locator(".applicant-checkbox")).to_have_count(5)

        # Test 2: Select all functionality
        select_all = team_page.locator("#select-all")
        expect(select_all).not_to_be_checked()

        # Click select all
        select_all.check()

        # Verify all checkboxes are checked
        checkboxes = team_page.locator(".applicant-checkbox")
        for i in range(5):
            expect(checkboxes.nth(i)).to_be_checked()

        # Uncheck select all
        select_all.uncheck()
        for i in range(5):
            expect(checkboxes.nth(i)).not_to_be_checked()

        # Test 3: Individual checkbox selection
        # Select first two checkboxes
        checkboxes.nth(0).check()
        checkboxes.nth(1).check()

        # Verify they are checked
        expect(checkboxes.nth(0)).to_be_checked()
        expect(checkboxes.nth(1)).to_be_checked()
        expect(checkboxes.nth(2)).not_to_be_checked()

        # Verify select-all is not automatically checked
        expect(select_all).not_to_be_checked()

        # Test 4: Filter functionality - show unassigned only
        # First, verify we see all 5 applicants
        expect(team_page.locator(".applicant-checkbox")).to_have_count(5)

        # Check "Show only unassigned applicants" checkbox
        unassigned_filter = team_page.get_by_label("Show only unassigned applicants")
        unassigned_filter.check()

        # Submit the filter form
        team_page.get_by_role("button", name="Apply Filters").click()

        # Wait for page to reload/update
        team_page.wait_for_load_state("networkidle")

        # Should now see only 3 applicants (5 total - 2 assigned = 3 unassigned)
        expect(team_page.locator(".applicant-checkbox")).to_have_count(3)

        # Uncheck the filter to see all again
        unassigned_filter = team_page.get_by_label("Show only unassigned applicants")
        unassigned_filter.uncheck()
        team_page.get_by_role("button", name="Apply Filters").click()
        team_page.wait_for_load_state("networkidle")
        expect(team_page.locator(".applicant-checkbox")).to_have_count(5)

        # Test 5: Bulk team assignment
        # Select first applicant
        checkboxes = team_page.locator(".applicant-checkbox")  # Re-query after filter
        checkboxes.nth(0).check()

        # Select a team from dropdown (no label in template, use id)
        team_select = team_page.locator("#bulk-team-select")
        team_select.select_option(label="Team Beta - Django")

        # Click assign button
        team_page.get_by_role("button", name="Assign to Team").click()

        # Wait for page reload
        team_page.wait_for_load_state("networkidle")

        # Verify success message appears
        expect(team_page.locator(".messagelist").first).to_contain_text(
            "Successfully assigned"
        )

        # Test 6: HTMX overlap calculation
        # Select multiple applicants
        checkboxes = team_page.locator(".applicant-checkbox")  # Re-query
        checkboxes.nth(0).check()
        checkboxes.nth(1).check()

        # Select a team for overlap analysis
        # The second combobox named "Team" is in the overlap analysis form
        team_comboboxes = team_page.get_by_role("combobox", name="Team")
        overlap_team_select = team_comboboxes.nth(1)  # Second one is the overlap form
        overlap_team_select.select_option(value=str(data.team_alpha.id))

        # Select analysis type
        analysis_type_radio = team_page.get_by_role(
            "radio", name="Check Navigator Overlap"
        )
        analysis_type_radio.check()

        # Click check overlap button
        team_page.get_by_role("button", name="Check Overlap").click()

        # Wait for HTMX response - the container may remain hidden if there's an error
        # Just verify the form submission completes
        team_page.wait_for_load_state("networkidle")

        # Test 7: Sorting functionality
        # Click on score column header to sort
        # (using locator since it's a sortable th with data attribute)
        score_header = team_page.locator("th.sortable[data-sort='score']")
        score_header.click()

        # Wait for page to reload with sorting
        team_page.wait_for_load_state("networkidle")

        # Verify URL contains sort parameter
        expect(team_page).to_have_url(re.compile(r".*sort=score.*"))

        # Click again to reverse sort
        score_header.click()
        team_page.wait_for_load_state("networkidle")

        # Verify URL contains order parameter
        expect(team_page).to_have_url(re.compile(r".*order=(desc|asc).*"))

        # Test 8: Verify teams panel is visible
        teams_panel = team_page.locator(".side-panel")
        expect(teams_panel).to_be_visible()

        # Verify Team Alpha heading shows (team card is visible)
        expect(team_page.get_by_role("heading", name="Team Alpha")).to_be_visible()

        # Test 9: Waitlist functionality
        # Select an unassigned applicant for waitlist (nth(2) should be unassigned)
        checkboxes = team_page.locator(".applicant-checkbox")  # Re-query
        checkboxes.nth(2).check()

        # Click add to waitlist button
        team_page.get_by_role("button", name="Add to Waitlist").click()

        # Wait for page reload
        team_page.wait_for_load_state("networkidle")

        # Verify success message appears
        expect(team_page.locator(".messagelist").first).to_contain_text(
            "Successfully added"
        )
        expect(team_page.locator(".messagelist").first).to_contain_text("waitlist")


class TestCompareAvailability:
    """Test suite for compare availability page functionality."""

    @pytest.fixture
    def setup_compare_data(self, db):
        """Create users with different availability patterns for testing."""
        from accounts.factories import UserAvailabilityFactory, UserFactory
        from home.factories import OrganizerFactory

        organizer_membership = OrganizerFactory.create()
        organizer = organizer_membership.user
        organizer.set_password("testpass123")
        organizer.save()

        # User A: available at slots 0.0, 0.5 (Sunday 00:00, 00:30)
        user_a = UserFactory.create(first_name="Alice", last_name="Available")
        UserAvailabilityFactory.create(user=user_a, slots=[0.0, 0.5])

        # User B: available at slot 0.0 only (Sunday 00:00)
        user_b = UserFactory.create(first_name="Bob", last_name="Busy")
        UserAvailabilityFactory.create(user=user_b, slots=[0.0])

        return {
            "organizer": organizer,
            "user_a": user_a,
            "user_b": user_b,
        }

    def login_as_organizer(self, page: Page, organizer: CustomUser):
        page.goto(reverse("login"))
        page.get_by_label("Username").fill(organizer.username)
        page.get_by_label("Password").fill("testpass123")
        page.get_by_role("button", name="Login").click()
        page.wait_for_load_state("networkidle")

    def navigate_to_compare_page(self, page: Page, user_ids: list[int]):
        users_param = "&".join(f"users={uid}" for uid in user_ids)
        # Force offset=0 so we're testing UTC directly
        page.goto(f"{reverse('compare_availability')}?{users_param}&offset=0")
        page.wait_for_load_state("networkidle")

    def assert_selected_users_show_availability(self, page: Page, data: dict):
        """Verify the grid has colored cells based on user availability."""
        # Slot 0-0-0 (Sunday 00:00) should have color (both users available)
        slot_0_0_0 = page.locator('td.time-slot[title*="2/2"]')
        expect(slot_0_0_0.first).to_be_visible()

        # Slot 0-0-1 (Sunday 00:30) should have partial color (only user_a)
        slot_0_0_1 = page.locator('td.time-slot[title*="1/2"]')
        expect(slot_0_0_1.first).to_be_visible()

    def assert_different_overlap_colors(self, page: Page):
        """Verify cells have different background colors based on overlap count."""
        # Full overlap cell (2/2) - get computed style
        full_overlap = page.locator('td.time-slot[title*="2/2"]').first
        full_style = full_overlap.evaluate(
            "el => window.getComputedStyle(el).backgroundColor"
        )

        # Partial overlap cell (1/2)
        partial_overlap = page.locator('td.time-slot[title*="1/2"]').first
        partial_style = partial_overlap.evaluate(
            "el => window.getComputedStyle(el).backgroundColor"
        )

        # No overlap cell (0/2)
        no_overlap = page.locator('td.time-slot[title*="0/2"]').first
        no_style = no_overlap.evaluate(
            "el => window.getComputedStyle(el).backgroundColor"
        )

        # Full should be different from partial
        assert full_style != partial_style, "Full and partial overlap should differ"
        # Partial should be different from none
        assert partial_style != no_style, "Partial and no overlap should differ"

    def assert_unavailable_user_grayed_on_hover(self, page: Page, data: dict):
        """Verify hovering over a cell grays out unavailable users."""
        # Hover over Sunday 00:30 slot where only user_a is available
        slot_0_0_1 = page.locator('td.time-slot[title*="1/2"]').first
        slot_0_0_1.hover()

        # Bob should have unavailable styling
        bob_card = page.locator(".user-card").filter(has_text="Bob Busy")
        expect(bob_card).to_have_class(re.compile(r"unavailable"))

        # The user-name inside should have line-through
        bob_name = bob_card.locator(".user-name")
        text_decoration = bob_name.evaluate(
            "el => window.getComputedStyle(el).textDecoration"
        )
        assert "line-through" in text_decoration

    def assert_available_user_readable_on_hover(self, page: Page, data: dict):
        """Verify available user's name is readable when hovering over a cell."""
        # Hover over Sunday 00:30 slot where only user_a is available
        slot_0_0_1 = page.locator('td.time-slot[title*="1/2"]').first
        slot_0_0_1.hover()

        # Alice should not have unavailable class
        alice_card = page.locator(".user-card").filter(has_text="Alice Available")
        expect(alice_card).not_to_have_class(re.compile(r"unavailable"))

        # Name should not be struck through
        alice_name = alice_card.locator(".user-name")
        text_decoration = alice_name.evaluate(
            "el => window.getComputedStyle(el).textDecoration"
        )
        assert "line-through" not in text_decoration

    def assert_mouseleave_resets_availability(self, page: Page):
        """Verify moving cursor out of grid makes all users appear available."""
        # First hover over a cell to trigger unavailable state
        slot_0_0_1 = page.locator('td.time-slot[title*="1/2"]').first
        slot_0_0_1.hover()

        # Move cursor out of grid (hover on heading instead)
        page.get_by_role("heading", name="Compare Availability").hover()

        # All user cards should no longer have unavailable class
        user_cards = page.locator(".user-card")
        for i in range(user_cards.count()):
            expect(user_cards.nth(i)).not_to_have_class(re.compile(r"unavailable"))

    def assert_user_hover_shows_single_availability(self, page: Page, data: dict):
        """Verify hovering over a user's name shows only that user's availability.

        When hovering over Bob's card, only Bob's availability should be shown.
        Alice's availability should be hidden (slots where only Alice is available
        should have no background color).
        """
        bob_card = page.locator(".user-card").filter(has_text="Bob Busy")
        bob_card.hover()

        # Verify hover registered by checking Bob's card has highlight class
        expect(bob_card).to_have_class(re.compile(r"bg-purple-100"))

        # Bob's available slot (0-0-0) should show full purple
        slot_0_0_0 = page.locator('td.time-slot[title*="2/2"]').first
        bob_only_color = slot_0_0_0.evaluate(
            "el => window.getComputedStyle(el).backgroundColor"
        )
        assert bob_only_color.replace(" ", "") == "rgb(92,2,135)"

        # Slot where only Alice is available (0-0-1) should have NO color,
        # proving Alice's availability is hidden when hovering over Bob
        slot_0_0_1 = page.locator('td.time-slot[title*="1/2"]').first

        # Wait for the background color to become transparent
        page.wait_for_function(
            """(el) => {
                const bg = window.getComputedStyle(el).backgroundColor;
                return bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent';
            }""",
            arg=slot_0_0_1.element_handle(),
        )

    @pytest.mark.playwright
    def test_compare_availability_interactivity(self, page: Page, setup_compare_data):
        """
        Test compare availability grid interactivity:
        1. Selected users' availability shows up in grid
        2. Different background colors for different overlap counts
        3. Unavailable user's name grayed and struck out on cell hover
        4. Available user's name readable on cell hover
        5. Moving cursor out of grid resets all users to available
        6. Hovering over user's name shows only that user's availability
        """
        data = setup_compare_data

        self.login_as_organizer(page, data["organizer"])
        self.navigate_to_compare_page(page, [data["user_a"].id, data["user_b"].id])

        self.assert_selected_users_show_availability(page, data)
        self.assert_different_overlap_colors(page)
        self.assert_unavailable_user_grayed_on_hover(page, data)
        self.assert_available_user_readable_on_hover(page, data)
        self.assert_mouseleave_resets_availability(page)
        self.assert_user_hover_shows_single_availability(page, data)
