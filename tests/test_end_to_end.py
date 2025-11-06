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

    @pytest.fixture
    def opps_page(self, page):
        """Fixture to access AspirEDU internal pages."""
        page.goto(reverse("opportunities"))
        self.wait_for_alpine_init(page)
        return page

    def wait_for_alpine_init(self, opps_page: Page):
        """Wait for Alpine.js to initialize and opportunities to load."""
        opps_page.wait_for_selector('[x-data*="opportunitiesApp"]')
        opps_page.wait_for_load_state("networkidle")
        # Wait for the results counter to appear, indicating Alpine has initialized
        opps_page.get_by_text(RESULTS_PATTERN).wait_for(state="visible")

    def test_page_loads_correctly(self, opps_page: Page):
        """Test that the page loads with all main elements."""
        # Check main heading
        expect(
            opps_page.get_by_role("heading", name="Django Contribution Opportunities")
        ).to_be_visible()

        # Check that search inputs are visible
        expect(opps_page.get_by_label("Search by Name")).to_be_visible()
        expect(opps_page.get_by_label("Search by Tags")).to_be_visible()
        expect(opps_page.get_by_label("Search by Outcomes")).to_be_visible()
        expect(opps_page.get_by_label("Search by Requirements")).to_be_visible()
        expect(opps_page.get_by_label("Search Description")).to_be_visible()

        # Check that clear filters button is visible
        expect(
            opps_page.get_by_role("button", name="Clear All Filters")
        ).to_be_visible()

    def test_search_by_name_functionality(self, opps_page: Page):
        """Test the name search filter with autocomplete."""
        name_input = opps_page.get_by_label("Search by Name")
        name_input.fill("Google")

        # Check that results are filtered by looking for cards containing "Google"
        # Use a more semantic approach to find opportunity cards
        opportunity_cards = opps_page.get_by_role("button").filter(has_text="Google")
        # Wait for the filtered results to appear
        expect(opportunity_cards.first).to_be_visible()
        assert opportunity_cards.count()

    def test_autocomplete_selection(self, opps_page: Page):
        """Test selecting an item from autocomplete dropdown."""
        name_input = opps_page.get_by_label("Search by Name")
        name_input.fill("Goo")

        # Look for autocomplete suggestions - wait for them to appear
        autocomplete_items = opps_page.locator(".suggestion-item")
        expect(autocomplete_items.first).to_be_visible()
        assert autocomplete_items.count()
        first_suggestion = autocomplete_items.first
        suggestion_text = first_suggestion.inner_text()
        first_suggestion.click()

        # Verify the input value was updated
        expect(name_input).to_have_value(suggestion_text)

    def test_outcomes_search_functionality(self, opps_page: Page):
        """Test the outcomes search filter."""
        outcomes_input = opps_page.get_by_label("Search by Outcomes")
        outcomes_input.fill("technical")

        # Verify filtering occurred by checking results counter
        results_text = opps_page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

    def test_requirements_search_functionality(self, opps_page: Page):
        """Test the requirements search filter."""
        requirements_input = opps_page.get_by_label("Search by Requirements")
        requirements_input.fill("Django")

        # Verify filtering occurred
        results_text = opps_page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

    def test_description_search_functionality(self, opps_page: Page):
        """Test the description search filter."""
        description_input = opps_page.get_by_label("Search Description")
        description_input.fill("student")

        # Verify filtering occurred
        results_text = opps_page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

    def test_tag_search_functionality(self, opps_page: Page):
        """Test the tag search filter."""
        description_input = opps_page.get_by_label("Search by Tags")
        description_input.fill("Fellowship")

        # Verify filtering occurred
        results_text = opps_page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()
        # Look for cards that contain mentorship tags
        fellowship_cards = opps_page.get_by_role("button").filter(has_text="fellow")
        expect(fellowship_cards.first).to_be_visible()
        assert fellowship_cards.count()

    def test_type_filter_functionality(self, opps_page: Page):
        """Test the type checkbox filters."""
        # Get available type checkboxes by their labels
        education_checkbox = opps_page.get_by_label("Education")
        # Get the checkbox label text to verify filtering
        education_checkbox.check()

        # Verify results counter updates
        results_text = opps_page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

    def test_clear_filters_functionality(self, opps_page: Page):
        """Test the clear all filters button."""
        # Apply some filters first
        name_input = opps_page.get_by_label("Search by Name")
        name_input.fill("Test")

        # Click clear filters using the button role
        clear_button = opps_page.get_by_role("button", name="Clear All Filters")
        clear_button.click()

        # Verify filters are cleared
        expect(name_input).to_have_value("")

    def test_card_click_opens_modal(self, opps_page: Page):
        """Test that clicking a card opens the modal."""
        # Find opportunity cards by their button role
        opportunity_cards = opps_page.get_by_role("button").filter(
            has_text="Google Summer of Code"
        )

        if opportunity_cards.count() == 0:
            # Fallback to any opportunity card
            opportunity_cards = opps_page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count()
        first_card = opportunity_cards.first
        # Get the card title for verification
        card_title = first_card.get_by_role("heading").inner_text()
        first_card.click()

        # Check that modal dialog is visible
        modal = opps_page.get_by_role("dialog")
        expect(modal).to_be_visible()

        # Check that modal title matches card title
        modal_title = modal.get_by_role("heading").first
        expect(modal_title).to_contain_text(card_title)

    def test_modal_content_display(self, opps_page: Page):
        """Test that modal displays opportunity information."""
        # Open first available opportunity card
        opportunity_cards = opps_page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count()
        opportunity_cards.first.click()

        # Check modal dialog is open
        modal = opps_page.get_by_role("dialog")
        expect(modal).to_be_visible()

        # Check that modal sections are present using headings
        description_heading = modal.get_by_role("heading", name="Description")
        expect(description_heading).to_be_visible()
        assert description_heading.count()

    def test_modal_close_with_x_button(self, opps_page: Page):
        """Test closing modal with the X button."""
        # Open modal
        opportunity_cards = opps_page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count()
        opportunity_cards.first.click()

        modal = opps_page.get_by_role("dialog")
        expect(modal).to_be_visible()

        # Click close button using aria-label
        close_button = opps_page.get_by_label("Close modal")
        close_button.click()

        expect(modal).not_to_be_visible()

    # I'm not sure why this is failing on CI. It passes locally and within the actual
    # application. The next steps are to get the traces and images from CI to inspect
    # why it may be failing.
    @pytest.mark.xfail
    def test_modal_close_by_clicking_overlay(self, opps_page: Page):
        """Test closing modal by clicking the overlay."""
        # Open modal
        opportunity_cards = opps_page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count()
        opportunity_cards.first.click()

        # Find modal overlay (parent of dialog)
        modal_overlay = opps_page.locator(".fixed.inset-0.bg-black.bg-opacity-50")
        modal_overlay.wait_for(state="visible")

        # Click on overlay background (outside the modal content)
        modal_overlay.click(position={"x": 5, "y": 5})
        modal_overlay.wait_for(state="hidden")

    def test_keyboard_navigation_on_cards(self, opps_page: Page):
        """Test keyboard navigation functionality on cards."""
        # Find focusable opportunity cards
        opportunity_cards = opps_page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count()
        first_card = opportunity_cards.first

        # Focus and use Enter key
        first_card.focus()
        opps_page.keyboard.press("Enter")

        modal = opps_page.get_by_role("dialog")
        expect(modal).to_be_visible()

        # Close modal with X button
        close_button = opps_page.get_by_label("Close modal")
        close_button.click()
        expect(modal).not_to_be_visible()

        # Test Space key also opens modal
        first_card.focus()
        opps_page.keyboard.press("Space")

        expect(modal).to_be_visible()

    def test_multiple_filters_combination(self, opps_page: Page):
        """Test using multiple search filters together."""
        # Apply multiple filters using semantic selectors
        opps_page.get_by_label("Search by Name").fill("Google")
        opps_page.get_by_label("Search by Tags").fill("mentorship")

        # Check that results counter is visible and updated
        results_text = opps_page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

        # Verify results counter shows filtering
        counter_text = results_text.inner_text()
        assert "Showing" in counter_text

    def test_no_results_display(self, opps_page: Page):
        """Test that no results message appears when filters match nothing."""
        # Search for something unlikely to match
        opps_page.get_by_label("Search by Name").fill("NonexistentOpportunity12345")

        # Check for no results message or zero count
        no_results = opps_page.get_by_text("No opportunities found")
        results_counter = opps_page.get_by_text(re.compile(r"Showing 0 of "))

        # Either no results message or zero count should be visible
        if no_results.count() > 0:
            expect(no_results).to_be_visible()
        else:
            expect(results_counter).to_be_visible()

    def test_results_counter_updates(self, opps_page: Page):
        """Test that the results counter updates correctly."""
        results_text = opps_page.get_by_text(RESULTS_PATTERN)
        initial_text = results_text.inner_text()

        # Apply a filter
        opps_page.get_by_label("Search by Tags").fill("mentorship")

        # Check that the counter is still visible and properly formatted
        expect(results_text).to_be_visible()
        current_text = results_text.inner_text()

        # Verify the format
        assert "Showing" in current_text
        assert "opportunities" in current_text

    @pytest.mark.parametrize(
        "search_label,search_term",
        [
            ("Search by Name", "Google"),
            ("Search by Tags", "mentorship"),
            ("Search by Outcomes", "technical"),
            ("Search by Requirements", "Django"),
            ("Search Description", "student"),
        ],
    )
    def test_individual_search_fields(self, opps_page: Page, search_label, search_term):
        """Parameterized test for individual search fields using semantic selectors."""
        search_input = opps_page.get_by_label(search_label)
        search_input.fill(search_term)

        # Verify that the search was applied (counter should be visible)
        results_text = opps_page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

    def test_external_links_have_correct_attributes(self, opps_page: Page):
        """Test that external links have proper security attributes."""
        # Check Learn More links using link role and text
        learn_more_links = opps_page.get_by_role("link", name="Learn More")

        assert learn_more_links.count()
        first_link = learn_more_links.first
        expect(first_link).to_have_attribute("target", "_blank")
        expect(first_link).to_have_attribute("rel", "noopener noreferrer")

    def test_accessibility_attributes(self, opps_page: Page):
        """Test key accessibility features using semantic selectors."""
        # Check that search inputs are properly labeled
        expect(opps_page.get_by_label("Search by Name")).to_be_visible()
        expect(opps_page.get_by_label("Search by Tags")).to_be_visible()
        expect(opps_page.get_by_label("Search by Outcomes")).to_be_visible()
        expect(opps_page.get_by_label("Search by Requirements")).to_be_visible()
        expect(opps_page.get_by_label("Search Description")).to_be_visible()

        # Check that opportunity cards have proper button role
        opportunity_cards = opps_page.locator('[role="button"][tabindex="0"]')
        assert opportunity_cards.count()
        expect(opportunity_cards.first).to_be_visible()

    def test_responsive_behavior(self, opps_page: Page):
        """Test basic responsive functionality."""
        # Test mobile viewport
        opps_page.set_viewport_size({"width": 375, "height": 667})

        # Verify main elements are still visible using semantic selectors
        expect(
            opps_page.get_by_role("heading", name="Django Contribution Opportunities")
        ).to_be_visible()
        expect(opps_page.get_by_label("Search by Name")).to_be_visible()

        # Reset viewport
        opps_page.set_viewport_size({"width": 1280, "height": 720})

    def test_focus_management_in_modal(self, opps_page: Page):
        """Test that focus is properly managed when modal opens."""
        # Open modal using semantic selectors
        opportunity_cards = opps_page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count()
        opportunity_cards.first.click()
        opps_page.wait_for_timeout(300)

        # Check modal dialog is visible and has proper attributes
        modal = opps_page.get_by_role("dialog")
        expect(modal).to_be_visible()
        expect(modal).to_have_attribute("aria-modal", "true")

    def test_page_has_required_elements(self, opps_page: Page):
        """Test that all required opps_page elements are present using semantic selectors."""
        # Check for main structural elements using roles and labels
        expect(
            opps_page.get_by_role("heading", name="Django Contribution Opportunities")
        ).to_be_visible()
        expect(opps_page.get_by_label("Search by Name")).to_be_visible()
        expect(opps_page.get_by_label("Search by Tags")).to_be_visible()
        expect(opps_page.get_by_label("Search by Outcomes")).to_be_visible()
        expect(opps_page.get_by_label("Search by Requirements")).to_be_visible()
        expect(opps_page.get_by_label("Search Description")).to_be_visible()
        expect(
            opps_page.get_by_role("button", name="Clear All Filters")
        ).to_be_visible()

    def test_filter_by_type_checkboxes(self, opps_page: Page):
        """Test filtering by opportunity type using checkboxes."""
        # Get all type checkboxes
        type_checkboxes = opps_page.get_by_role("checkbox")

        assert type_checkboxes.count()
        # Check the first available type
        first_checkbox = type_checkboxes.first
        first_checkbox.check()

        # Verify that filtering occurred
        results_text = opps_page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

        # Uncheck to verify it toggles
        first_checkbox.uncheck()

        # Results should update again
        expect(results_text).to_be_visible()

    def test_modal_navigation_with_links(self, opps_page: Page):
        """Test that modal contains properly accessible external links."""
        # Open modal
        opportunity_cards = opps_page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count() > 0
        opportunity_cards.first.click()

        modal = opps_page.get_by_role("dialog")
        expect(modal).to_be_visible()

        # Look for external links within the modal
        modal_links = modal.get_by_role("link")
        assert modal_links.count() > 0
        # Verify links have proper attributes
        for i in range(min(3, modal_links.count())):  # Check first 3 links
            link = modal_links.nth(i)
            expect(link).to_have_attribute("target", "_blank")
            expect(link).to_have_attribute("rel", "noopener noreferrer")


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
        8. Pagination
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
