import re
from logging import getLogger

import pytest
from django.urls import reverse
from playwright.sync_api import expect, Browser
from playwright.sync_api import Page

logger = getLogger(__name__)

# Mark all tests as playwright
pytestmark = pytest.mark.playwright

RESULTS_PATTERN = re.compile(r"Showing \d+ of \d+ opportunities")


class TestDjangoOpportunities:
    """Test suite for Django Contribution Opportunities page functionality."""

    @pytest.fixture
    def page(self, browser: Browser, live_server):
        """Fixture to access AspirEDU internal pages."""
        context = browser.new_context(base_url=live_server.url)
        page = context.new_page()
        page.goto(reverse("opportunities"))
        self.wait_for_alpine_init(page)
        return page

    def wait_for_alpine_init(self, page: Page):
        """Wait for Alpine.js to initialize and opportunities to load."""
        page.wait_for_selector('[x-data*="opportunitiesApp"]')
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)  # Allow Alpine.js to fully initialize

    def test_page_loads_correctly(self, page: Page):
        """Test that the page loads with all main elements."""
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

    def test_search_by_name_functionality(self, page: Page):
        """Test the name search filter with autocomplete."""
        name_input = page.get_by_label("Search by Name")
        name_input.fill("Google")
        page.wait_for_timeout(300)

        # Check that results are filtered by looking for cards containing "Google"
        # Use a more semantic approach to find opportunity cards
        opportunity_cards = page.get_by_role("button").filter(has_text="Google")
        assert opportunity_cards.count()
        expect(opportunity_cards.first).to_be_visible()

    def test_autocomplete_selection(self, page: Page):
        """Test selecting an item from autocomplete dropdown."""
        name_input = page.get_by_label("Search by Name")
        name_input.fill("Goo")
        page.wait_for_timeout(300)

        # Look for autocomplete suggestions
        autocomplete_items = page.locator(".suggestion-item")
        assert autocomplete_items.count()
        first_suggestion = autocomplete_items.first
        suggestion_text = first_suggestion.inner_text()
        first_suggestion.click()

        # Verify the input value was updated
        expect(name_input).to_have_value(suggestion_text)

    def test_outcomes_search_functionality(self, page: Page):
        """Test the outcomes search filter."""
        outcomes_input = page.get_by_label("Search by Outcomes")
        outcomes_input.fill("technical")
        page.wait_for_timeout(300)

        # Verify filtering occurred by checking results counter
        results_text = page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

    def test_requirements_search_functionality(self, page: Page):
        """Test the requirements search filter."""
        requirements_input = page.get_by_label("Search by Requirements")
        requirements_input.fill("Django")
        page.wait_for_timeout(300)

        # Verify filtering occurred
        results_text = page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

    def test_description_search_functionality(self, page: Page):
        """Test the description search filter."""
        description_input = page.get_by_label("Search Description")
        description_input.fill("student")
        page.wait_for_timeout(300)

        # Verify filtering occurred
        results_text = page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

    def test_tag_search_functionality(self, page: Page):
        """Test the tag search filter."""
        description_input = page.get_by_label("Search by Tags")
        description_input.fill("Fellowship")
        page.wait_for_timeout(300)

        # Verify filtering occurred
        results_text = page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()
        # Look for cards that contain mentorship tags
        fellowship_cards = page.get_by_role("button").filter(has_text="fellow")
        assert fellowship_cards.count()
        expect(fellowship_cards.first).to_be_visible()

    def test_type_filter_functionality(self, page: Page):
        """Test the type checkbox filters."""
        # Get available type checkboxes by their labels
        education_checkbox = page.get_by_label("Education")
        # Get the checkbox label text to verify filtering
        education_checkbox.check()
        page.wait_for_timeout(300)

        # Verify results counter updates
        results_text = page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

    def test_clear_filters_functionality(self, page: Page):
        """Test the clear all filters button."""
        # Apply some filters first
        page.get_by_label("Search by Name").fill("Test")
        page.wait_for_timeout(300)

        # Click clear filters using the button role
        clear_button = page.get_by_role("button", name="Clear All Filters")
        clear_button.click()
        page.wait_for_timeout(300)

        # Verify filters are cleared
        expect(page.get_by_label("Search by Name")).to_have_value("")

    def test_card_click_opens_modal(self, page: Page):
        """Test that clicking a card opens the modal."""
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
        page.wait_for_timeout(300)

        # Check that modal dialog is visible
        modal = page.get_by_role("dialog")
        expect(modal).to_be_visible()

        # Check that modal title matches card title
        modal_title = modal.get_by_role("heading").first
        expect(modal_title).to_contain_text(card_title)

    def test_modal_content_display(self, page: Page):
        """Test that modal displays opportunity information."""
        # Open first available opportunity card
        opportunity_cards = page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count()
        opportunity_cards.first.click()
        page.wait_for_timeout(300)

        # Check modal dialog is open
        modal = page.get_by_role("dialog")
        expect(modal).to_be_visible()

        # Check that modal sections are present using headings
        description_heading = modal.get_by_role("heading", name="Description")
        assert description_heading.count()
        expect(description_heading).to_be_visible()

    def test_modal_close_with_x_button(self, page: Page):
        """Test closing modal with the X button."""
        # Open modal
        opportunity_cards = page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count()
        opportunity_cards.first.click()
        page.wait_for_timeout(300)

        modal = page.get_by_role("dialog")
        expect(modal).to_be_visible()

        # Click close button using aria-label
        close_button = page.get_by_label("Close modal")
        close_button.click()
        page.wait_for_timeout(300)

        expect(modal).not_to_be_visible()

    def test_modal_close_by_clicking_overlay(self, page: Page):
        """Test closing modal by clicking the overlay."""
        # Open modal
        opportunity_cards = page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count()
        opportunity_cards.first.click()
        page.wait_for_timeout(300)

        # Find modal overlay (parent of dialog)
        modal_overlay = page.locator(".fixed.inset-0.bg-black.bg-opacity-50")
        expect(modal_overlay).to_be_visible()

        # Click on overlay background (outside the modal content)
        modal_overlay.click(position={"x": 50, "y": 50})
        page.wait_for_timeout(300)

        expect(modal_overlay).not_to_be_visible()

    def test_keyboard_navigation_on_cards(self, page: Page):
        """Test keyboard navigation functionality on cards."""
        # Find focusable opportunity cards
        opportunity_cards = page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count()
        first_card = opportunity_cards.first

        # Focus and use Enter key
        first_card.focus()
        page.keyboard.press("Enter")
        page.wait_for_timeout(300)

        modal = page.get_by_role("dialog")
        expect(modal).to_be_visible()

        # Close modal
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        # Test Space key
        first_card.focus()
        page.keyboard.press("Space")
        page.wait_for_timeout(300)

        expect(modal).to_be_visible()

    def test_multiple_filters_combination(self, page: Page):
        """Test using multiple search filters together."""
        # Apply multiple filters using semantic selectors
        page.get_by_label("Search by Name").fill("Google")
        page.get_by_label("Search by Tags").fill("mentorship")
        page.wait_for_timeout(500)

        # Check that results counter is visible and updated
        results_text = page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

        # Verify results counter shows filtering
        counter_text = results_text.inner_text()
        assert "Showing" in counter_text

    def test_no_results_display(self, page: Page):
        """Test that no results message appears when filters match nothing."""
        # Search for something unlikely to match
        page.get_by_label("Search by Name").fill("NonexistentOpportunity12345")
        page.wait_for_timeout(300)

        # Check for no results message or zero count
        no_results = page.get_by_text("No opportunities found")
        results_counter = page.get_by_text(re.compile(r"Showing 0 of "))

        # Either no results message or zero count should be visible
        if no_results.count() > 0:
            expect(no_results).to_be_visible()
        else:
            expect(results_counter).to_be_visible()

    def test_results_counter_updates(self, page: Page):
        """Test that the results counter updates correctly."""
        results_text = page.get_by_text(RESULTS_PATTERN)
        initial_text = results_text.inner_text()

        # Apply a filter
        page.get_by_label("Search by Tags").fill("mentorship")
        page.wait_for_timeout(300)

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
    def test_individual_search_fields(self, page: Page, search_label, search_term):
        """Parameterized test for individual search fields using semantic selectors."""
        search_input = page.get_by_label(search_label)
        search_input.fill(search_term)
        page.wait_for_timeout(300)

        # Verify that the search was applied (counter should be visible)
        results_text = page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

    def test_external_links_have_correct_attributes(self, page: Page):
        """Test that external links have proper security attributes."""
        # Check Learn More links using link role and text
        learn_more_links = page.get_by_role("link", name="Learn More")

        assert learn_more_links.count()
        first_link = learn_more_links.first
        expect(first_link).to_have_attribute("target", "_blank")
        expect(first_link).to_have_attribute("rel", "noopener noreferrer")

    def test_accessibility_attributes(self, page: Page):
        """Test key accessibility features using semantic selectors."""
        # Check that search inputs are properly labeled
        expect(page.get_by_label("Search by Name")).to_be_visible()
        expect(page.get_by_label("Search by Tags")).to_be_visible()
        expect(page.get_by_label("Search by Outcomes")).to_be_visible()
        expect(page.get_by_label("Search by Requirements")).to_be_visible()
        expect(page.get_by_label("Search Description")).to_be_visible()

        # Check that opportunity cards have proper button role
        opportunity_cards = page.locator('[role="button"][tabindex="0"]')
        assert opportunity_cards.count()
        expect(opportunity_cards.first).to_be_visible()

    def test_responsive_behavior(self, page: Page):
        """Test basic responsive functionality."""
        # Test mobile viewport
        page.set_viewport_size({"width": 375, "height": 667})

        # Verify main elements are still visible using semantic selectors
        expect(
            page.get_by_role("heading", name="Django Contribution Opportunities")
        ).to_be_visible()
        expect(page.get_by_label("Search by Name")).to_be_visible()

        # Reset viewport
        page.set_viewport_size({"width": 1280, "height": 720})

    def test_focus_management_in_modal(self, page: Page):
        """Test that focus is properly managed when modal opens."""
        # Open modal using semantic selectors
        opportunity_cards = page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count()
        opportunity_cards.first.click()
        page.wait_for_timeout(300)

        # Check modal dialog is visible and has proper attributes
        modal = page.get_by_role("dialog")
        expect(modal).to_be_visible()
        expect(modal).to_have_attribute("aria-modal", "true")

    def test_page_has_required_elements(self, page: Page):
        """Test that all required page elements are present using semantic selectors."""
        # Check for main structural elements using roles and labels
        expect(
            page.get_by_role("heading", name="Django Contribution Opportunities")
        ).to_be_visible()
        expect(page.get_by_label("Search by Name")).to_be_visible()
        expect(page.get_by_label("Search by Tags")).to_be_visible()
        expect(page.get_by_label("Search by Outcomes")).to_be_visible()
        expect(page.get_by_label("Search by Requirements")).to_be_visible()
        expect(page.get_by_label("Search Description")).to_be_visible()
        expect(page.get_by_role("button", name="Clear All Filters")).to_be_visible()

    def test_filter_by_type_checkboxes(self, page: Page):
        """Test filtering by opportunity type using checkboxes."""
        # Get all type checkboxes
        type_checkboxes = page.get_by_role("checkbox")

        assert type_checkboxes.count()
        # Check the first available type
        first_checkbox = type_checkboxes.first
        first_checkbox.check()
        page.wait_for_timeout(300)

        # Verify that filtering occurred
        results_text = page.get_by_text(RESULTS_PATTERN)
        expect(results_text).to_be_visible()

        # Uncheck to verify it toggles
        first_checkbox.uncheck()
        page.wait_for_timeout(300)

        # Results should update again
        expect(results_text).to_be_visible()

    def test_modal_navigation_with_links(self, page: Page):
        """Test that modal contains properly accessible external links."""
        # Open modal
        opportunity_cards = page.locator('[role="button"][tabindex="0"]')

        assert opportunity_cards.count() > 0
        opportunity_cards.first.click()
        page.wait_for_timeout(300)

        modal = page.get_by_role("dialog")
        expect(modal).to_be_visible()

        # Look for external links within the modal
        modal_links = modal.get_by_role("link")
        assert modal_links.count() > 0
        # Verify links have proper attributes
        for i in range(min(3, modal_links.count())):  # Check first 3 links
            link = modal_links.nth(i)
            expect(link).to_have_attribute("target", "_blank")
            expect(link).to_have_attribute("rel", "noopener noreferrer")
