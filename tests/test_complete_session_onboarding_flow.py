"""
Comprehensive end-to-end test for the complete Djangonaut Space session flow.

This test validates the entire user journey from signup through team formation to accessing
team information. It creates minimal data through the web UI (signups, applications, availability)
and uses programmatic creation for admin setup (session, survey, teams) to keep the test
focused, fast, and maintainable.

PHASES TESTED:
1. Navigator and Captain signup, email confirmation, and availability setting
2. Session/survey/team/project setup (programmatic)
3. Three djangonauts signup, apply to session, set availability
4. Team formation via admin UI:
   - Super user uses team formation page to create a team with djangonaut A
   - Super user adds djangonaut B to waitlist
   - Super user sends session results notification
   - Djangonaut A accepts the invitation via web app
   - Super user assigns djangonaut B to team via team formation page
   - Super user sends acceptance email to djangonaut B
   - Djangonaut B accepts the invitation via web app
   - Super user sends team welcome emails
5. All team members (navigator, captain, djangonauts, organizer) verify access to team info
6. Timezone toggle JavaScript functionality on team detail page:
   - Verify initial timezone detection and display
   - Test toggle button switches between user timezone and UTC
   - Verify button text updates correctly
   - Confirm HTMX requests complete successfully

This test takes ~60s to run due to Wagtail integration and migrations.

Run with:
  # Headless
  uv run pytest -m playwright tests/test_complete_session_onboarding_flow.py

  # Visual debugging
  uv run pytest -m playwright tests/test_complete_session_onboarding_flow.py \
    --headed

  # Pause for exploration
  uv run pytest -m playwright tests/test_complete_session_onboarding_flow.py \
    --headed \
    --pause-at-end
"""

import re
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from playwright.sync_api import BrowserContext, Page, expect

from accounts.models import CustomUser
from accounts.tokens import account_activation_token
from home.models import Project, Question, Session, SessionMembership, Survey, Team

pytestmark = pytest.mark.playwright


@pytest.fixture
def context(new_context, live_server) -> BrowserContext:
    """Configure the playwright context."""
    return new_context(base_url=live_server.url)


@pytest.fixture
def page(context: BrowserContext):
    """Fixture to provide a browser page."""
    page = context.new_page()
    yield page
    page.close()
    context.close()


class TestCompleteSessionOnboardingFlow:
    """Test the complete session onboarding flow from signup to team access."""

    def signup_and_confirm_user(
        self,
        page: Page,
        username: str,
        email: str,
        first_name: str,
        last_name: str,
    ) -> CustomUser:
        """
        Helper to sign up a user and confirm their email.

        Returns the created user instance.
        """
        # Clear mail outbox
        mail.outbox.clear()

        # Navigate to signup page
        page.goto(reverse("signup"))
        page.wait_for_load_state("networkidle")

        # Fill in signup form (using locators instead of labels for reliability)
        page.locator("#id_username").fill(username)
        page.locator("#id_email").fill(email)
        page.locator("#id_first_name").fill(first_name)
        page.locator("#id_last_name").fill(last_name)
        page.locator("#id_password1").fill("testpass123")
        page.locator("#id_password2").fill("testpass123")
        page.locator("#id_accepted_coc").check()
        page.locator("#id_email_consent").check()

        # Submit form
        page.get_by_role("button", name="Submit").click()
        page.wait_for_load_state("networkidle")

        # Verify confirmation message
        expect(page.locator("body")).to_contain_text("Please check your email")

        # Get the user from database
        user = CustomUser.objects.get(username=username)

        # Extract activation link from email
        assert len(mail.outbox) == 1
        email_body = mail.outbox[0].body

        # Generate activation URL
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = account_activation_token.make_token(user)
        activation_url = reverse(
            "activate_account",
            kwargs={"uidb64": uid, "token": token},
        )

        # Visit activation link
        page.goto(activation_url)
        page.wait_for_load_state("networkidle")

        # Verify user is confirmed
        user.refresh_from_db()
        assert user.profile.email_confirmed is True

        return user

    def logout(self, page: Page):
        """Helper to logout - uses POST request as required by Django."""
        # Navigate to a page with a logout form/link
        page.goto(reverse("profile"))
        page.wait_for_load_state("networkidle")

        # Look for logout link/button and click it
        # This will typically be in the navigation
        logout_link = page.get_by_role(
            "link", name=re.compile(r"log out", re.IGNORECASE)
        )
        if logout_link.count() > 0:
            logout_link.click()
            page.wait_for_load_state("networkidle")
        else:
            # Fallback: just clear cookies/session programmatically
            page.context.clear_cookies()

    def set_availability(self, page: Page, username: str):
        """Helper to login and set availability for a user."""
        # Login
        page.goto(reverse("login"))
        page.locator("#id_username").fill(username)
        page.locator("#id_password").fill("testpass123")
        page.get_by_role("button", name="Login").click()
        page.wait_for_load_state("networkidle")

        # Navigate to availability page
        page.goto(reverse("availability"))
        page.wait_for_load_state("networkidle")

        # Wait for grid to load
        page.locator("#availability-grid tbody tr").first.wait_for(state="visible")
        page.locator(".time-slot[data-day][data-hour]").first.wait_for(state="visible")

        # Select some availability slots (Monday 9 AM - 10 AM)
        monday_9am = page.locator('.time-slot[data-day="1"][data-hour="9"]')
        monday_10am = page.locator('.time-slot[data-day="1"][data-hour="10"]')
        monday_9am.drag_to(monday_10am)
        page.wait_for_timeout(200)

        # Save availability
        page.get_by_role("button", name="Save Availability").first.click()
        page.wait_for_load_state("networkidle")

    def admin_login(self, page: Page, admin_user: CustomUser):
        """Helper to login as admin."""
        page.goto("/django-admin/")
        page.get_by_role("textbox", name="username").fill(admin_user.username)
        page.get_by_role("textbox", name="password").fill("testpass123")
        page.get_by_role("button", name="Log in").click()
        page.wait_for_load_state("networkidle")

    def admin_create_project(self, page: Page, name: str, url: str) -> int:
        """
        Helper to create a Project via Django admin.

        Returns the project ID.
        """
        # Navigate to Project add page
        page.goto("/django-admin/home/project/add/")
        page.wait_for_load_state("networkidle")

        # Fill in the form
        page.locator("#id_name").fill(name)
        page.locator("#id_url").fill(url)

        # Save
        page.get_by_role("button", name="Save", exact=True).click()
        page.wait_for_load_state("networkidle")

        # Verify success
        expect(page.locator(".messagelist")).to_contain_text("was added successfully")

        # Get project from database by name
        project = Project.objects.get(name=name)
        return project.id

    def admin_create_session(
        self,
        page: Page,
        title: str,
        slug: str,
        start_date: str,
        end_date: str,
        app_start_date: str,
        app_end_date: str,
        invitation_date: str,
    ) -> int:
        """
        Helper to create a Session via Django admin.

        Dates should be in YYYY-MM-DD format.
        Returns the session ID.
        """
        # Navigate to Session add page
        page.goto("/django-admin/home/session/add/")
        page.wait_for_load_state("networkidle")

        # Fill in the form
        page.locator("#id_title").fill(title)
        page.locator("#id_slug").fill(slug)
        page.locator("#id_start_date").fill(start_date)
        page.locator("#id_end_date").fill(end_date)
        page.locator("#id_application_start_date").fill(app_start_date)
        page.locator("#id_application_end_date").fill(app_end_date)
        page.locator("#id_invitation_date").fill(invitation_date)

        # Save
        page.get_by_role("button", name="Save", exact=True).click()
        page.wait_for_load_state("networkidle")

        # Verify success
        expect(page.locator(".messagelist")).to_contain_text("was added successfully")

        # Get session from database by slug
        session = Session.objects.get(slug=slug)
        return session.id

    def admin_create_survey_with_questions(
        self,
        page: Page,
        name: str,
        description: str,
        session_id: int,
        questions: list[dict],
    ) -> int:
        """
        Helper to create a Survey with questions via Django admin.

        questions is a list of dicts with keys: label, type_field, ordering, required
        Returns the survey ID.
        """
        # Navigate to Survey add page
        page.goto("/django-admin/home/survey/add/")
        page.wait_for_load_state("networkidle")

        # Fill in survey fields
        page.locator("#id_name").fill(name)
        page.locator("#id_description").fill(description)
        page.locator("#id_session").select_option(str(session_id))

        # Add questions via inline forms
        # QuestionInline has extra=0, so we need to click "Add another" for each question
        for i, question in enumerate(questions):
            # Click "Add another Question" link
            # Look for the add row link - it should be visible
            add_link = page.get_by_text("Add another Question")
            add_link.click()
            page.wait_for_timeout(500)  # Wait for the new form to be added

            # Fill in question fields
            # The fields should now be visible
            page.locator(f"#id_questions-{i}-label").fill(question["label"])
            page.locator(f"#id_questions-{i}-type_field").select_option(
                question["type_field"]
            )
            page.locator(f"#id_questions-{i}-ordering").fill(str(question["ordering"]))

            # Handle required checkbox
            required_checkbox = page.locator(f"#id_questions-{i}-required")
            if question.get("required", True):
                if not required_checkbox.is_checked():
                    required_checkbox.check()
            else:
                if required_checkbox.is_checked():
                    required_checkbox.uncheck()

        # Save
        page.get_by_role("button", name="Save", exact=True).click()
        page.wait_for_load_state("networkidle")

        # Verify success
        expect(page.locator(".messagelist")).to_contain_text("was added successfully")

        # Get survey from database by name
        survey = Survey.objects.get(name=name)
        return survey.id

    def admin_create_team(
        self, page: Page, name: str, session_id: int, project_id: int
    ) -> int:
        """
        Helper to create a Team via Django admin.

        Returns the team ID.
        """
        # Navigate to Team add page
        page.goto("/django-admin/home/team/add/")
        page.wait_for_load_state("networkidle")

        # Fill in the form
        page.locator("#id_name").fill(name)
        page.locator("#id_session").select_option(str(session_id))
        page.locator("#id_project").select_option(str(project_id))
        page.locator("#id_google_drive_folder").fill("https://www.google.com")

        # Save
        page.get_by_role("button", name="Save", exact=True).click()
        page.wait_for_load_state("networkidle")

        # Verify success
        expect(page.locator(".messagelist")).to_contain_text("was added successfully")

        # Get team from database by name and session
        team = Team.objects.get(name=name, session_id=session_id)
        return team.id

    def admin_update_session_application_survey(
        self, page: Page, session_id: int, survey_id: int
    ):
        """Helper to update a Session's application_survey field via Django admin."""
        # Navigate to Session change page
        page.goto(f"/django-admin/home/session/{session_id}/change/")
        page.wait_for_load_state("networkidle")

        # Update application survey
        page.locator("#id_application_survey").select_option(str(survey_id))

        # Save
        page.get_by_role("button", name="Save", exact=True).click()
        page.wait_for_load_state("networkidle")

        # Verify success
        expect(page.locator(".messagelist")).to_contain_text("was changed successfully")

    def admin_add_session_membership(
        self,
        page: Page,
        session_id: int,
        user_id: int,
        role: str,
        team_id: int | None = None,
    ):
        """
        Helper to add a SessionMembership via Django admin.

        Creates the membership directly via the SessionMembership admin add page.
        role should be one of: 'Captain', 'Navigator', 'Djangonaut', 'Organizer'
        """
        # Navigate to SessionMembership add page
        page.goto("/django-admin/home/sessionmembership/add/")
        page.wait_for_load_state("networkidle")

        # Fill in the membership fields
        page.locator("#id_user").select_option(str(user_id))
        page.locator("#id_session").select_option(str(session_id))
        page.locator("#id_role").select_option(role)

        if team_id is not None:
            page.locator("#id_team").select_option(str(team_id))

        # Set accepted to True (it's a select field, not a checkbox)
        page.locator("#id_accepted").select_option("true")

        # Save
        page.get_by_role("button", name="Save", exact=True).click()
        page.wait_for_load_state("networkidle")

        # Verify success
        expect(page.locator(".messagelist")).to_contain_text("was added successfully")

    def _navigator_signs_up_and_sets_availability(self, page: Page) -> CustomUser:
        """Navigator signs up, confirms email, sets availability, and logs out."""
        navigator = self.signup_and_confirm_user(
            page, "navigator1", "navigator1@test.com", "Nav", "One"
        )
        self.set_availability(page, "navigator1")
        self.logout(page)
        return navigator

    def _captain_signs_up_and_sets_availability(self, page: Page) -> CustomUser:
        """Captain signs up, confirms email, sets availability, and logs out."""
        captain = self.signup_and_confirm_user(
            page, "captain1", "captain1@test.com", "Cap", "One"
        )
        self.set_availability(page, "captain1")
        self.logout(page)
        return captain

    def _admin_creates_session(self, page: Page) -> tuple[CustomUser, Session]:
        """
        Admin logs in and creates a session with application period active.

        Returns:
            Tuple of (superuser, session) objects
        """
        # Create superuser programmatically (can't create via admin since we need to login first)
        superuser = CustomUser.objects.create_user(
            username="admin",
            email="admin@test.com",
            password="testpass123",
            first_name="Admin",
            last_name="User",
            is_superuser=True,
            is_staff=True,
        )
        superuser.profile.email_confirmed = True
        superuser.profile.save()

        # Login as admin
        self.admin_login(page, superuser)

        # Calculate dates for session
        now = timezone.now().date()
        app_start = now - timedelta(days=5)
        app_end = now + timedelta(days=5)
        session_start = app_end
        session_end = app_end + timedelta(days=60)
        invitation_date = app_end - timedelta(days=1)

        # Create session via admin
        session_id = self.admin_create_session(
            page,
            title="Test Session 2024",
            slug="test-session-2024",
            start_date=session_start.isoformat(),
            end_date=session_end.isoformat(),
            app_start_date=app_start.isoformat(),
            app_end_date=app_end.isoformat(),
            invitation_date=invitation_date.isoformat(),
        )

        # Get session object from database
        session = Session.objects.get(id=session_id)

        return superuser, session

    def _admin_creates_application_survey(self, page: Page, session: Session) -> Survey:
        """
        Admin creates application survey with questions and associates it with session.

        Returns:
            Survey object
        """
        # Create survey with questions via admin
        survey_id = self.admin_create_survey_with_questions(
            page,
            name="Application Survey",
            description="Please complete this application",
            session_id=session.id,
            questions=[
                {
                    "label": "Why do you want to join?",
                    "type_field": "TEXT",
                    "ordering": 1,
                    "required": True,
                },
                {
                    "label": "What is your experience level?",
                    "type_field": "TEXT",
                    "ordering": 2,
                    "required": True,
                },
            ],
        )

        # Update session with application survey via admin
        self.admin_update_session_application_survey(
            page,
            session_id=session.id,
            survey_id=survey_id,
        )

        # Get survey object from database
        survey = Survey.objects.get(id=survey_id)

        return survey

    def _admin_creates_project_and_team(
        self, page: Page, session: Session
    ) -> tuple[Project, Team]:
        """
        Admin creates a project and team for the session.

        Returns:
            Tuple of (project, team) objects
        """
        # Create project via admin
        project_id = self.admin_create_project(
            page,
            name="Django",
            url="https://github.com/django/django",
        )

        # Create team via admin
        team_id = self.admin_create_team(
            page,
            name="Team Alpha",
            session_id=session.id,
            project_id=project_id,
        )

        # Get objects from database
        project = Project.objects.get(id=project_id)
        team = Team.objects.get(id=team_id)

        return project, team

    def _admin_adds_navigator_and_captain_to_team(
        self,
        page: Page,
        session: Session,
        team: Team,
        navigator: CustomUser,
        captain: CustomUser,
    ):
        """Admin adds navigator and captain as members of the team."""
        # Add navigator as session member via admin
        self.admin_add_session_membership(
            page,
            session_id=session.id,
            user_id=navigator.id,
            role="Navigator",
            team_id=team.id,
        )

        # Add captain as session member via admin
        self.admin_add_session_membership(
            page,
            session_id=session.id,
            user_id=captain.id,
            role="Captain",
            team_id=team.id,
        )

    def _admin_adds_themselves_as_organizer(
        self, page: Page, superuser: CustomUser, session: Session
    ):
        """Admin adds themselves as an organizer (without a team) and logs out."""
        # Add superuser as organizer (no team) via admin
        self.admin_add_session_membership(
            page,
            session_id=session.id,
            user_id=superuser.id,
            role="Organizer",
            team_id=None,
        )

        # Logout admin
        self.logout(page)

    def _djangonaut_a_applies_to_session(
        self, page: Page, survey: Survey
    ) -> CustomUser:
        """Djangonaut A signs up, applies to session, sets availability, and logs out."""
        # Get the survey questions for form filling
        question1 = Question.objects.get(
            survey=survey, label="Why do you want to join?"
        )
        question2 = Question.objects.get(
            survey=survey, label="What is your experience level?"
        )

        survey_url = reverse("survey_response_create", kwargs={"slug": survey.slug})

        # Signup
        djangonaut_a = self.signup_and_confirm_user(
            page, "djangonaut_a", "djangonaut_a@test.com", "Django", "A"
        )

        # Apply to session
        page.goto(survey_url)
        page.wait_for_load_state("networkidle")

        page.wait_for_selector(f"#id_field_survey_{question1.id}", timeout=10000)
        page.fill(
            f"#id_field_survey_{question1.id}", "I want to learn Django and contribute"
        )
        page.fill(f"#id_field_survey_{question2.id}", "Beginner")
        page.get_by_role("button", name="Submit").click()
        page.wait_for_load_state("networkidle")

        # Set availability and logout
        self.set_availability(page, "djangonaut_a")
        self.logout(page)

        return djangonaut_a

    def _djangonaut_b_applies_to_session(
        self, page: Page, survey: Survey
    ) -> CustomUser:
        """Djangonaut B signs up, applies to session, sets availability, and logs out."""
        # Get the survey questions for form filling
        question1 = Question.objects.get(
            survey=survey, label="Why do you want to join?"
        )
        question2 = Question.objects.get(
            survey=survey, label="What is your experience level?"
        )

        survey_url = reverse("survey_response_create", kwargs={"slug": survey.slug})

        # Signup
        djangonaut_b = self.signup_and_confirm_user(
            page, "djangonaut_b", "djangonaut_b@test.com", "Django", "B"
        )

        # Apply to session
        page.goto(survey_url)
        page.wait_for_load_state("networkidle")

        page.fill(f"#id_field_survey_{question1.id}", "I love Python and want to help")
        page.fill(f"#id_field_survey_{question2.id}", "Intermediate")
        page.get_by_role("button", name="Submit").click()
        page.wait_for_load_state("networkidle")

        # Set availability and logout
        self.set_availability(page, "djangonaut_b")
        self.logout(page)

        return djangonaut_b

    def _djangonaut_c_applies_to_session(
        self, page: Page, survey: Survey
    ) -> CustomUser:
        """Djangonaut C signs up, applies to session, sets availability, and logs out."""
        # Get the survey questions for form filling
        question1 = Question.objects.get(
            survey=survey, label="Why do you want to join?"
        )
        question2 = Question.objects.get(
            survey=survey, label="What is your experience level?"
        )

        survey_url = reverse("survey_response_create", kwargs={"slug": survey.slug})

        # Signup
        djangonaut_c = self.signup_and_confirm_user(
            page, "djangonaut_c", "djangonaut_c@test.com", "Django", "C"
        )

        # Apply to session
        page.goto(survey_url)
        page.wait_for_load_state("networkidle")

        page.fill(
            f"#id_field_survey_{question1.id}", "I want to be part of the community"
        )
        page.fill(f"#id_field_survey_{question2.id}", "Advanced")
        page.get_by_role("button", name="Submit").click()
        page.wait_for_load_state("networkidle")

        # Set availability and logout
        self.set_availability(page, "djangonaut_c")
        self.logout(page)

        return djangonaut_c

    def _admin_assigns_djangonaut_a_to_team(
        self,
        page: Page,
        superuser: CustomUser,
        session: Session,
        team: Team,
        project: Project,
        djangonaut_a: CustomUser,
    ):
        """Admin logs in, assigns djangonaut A to team."""
        # Login as admin
        self.admin_login(page, superuser)

        # Navigate to session admin and use form teams action
        page.goto("/django-admin/home/session/")
        page.wait_for_load_state("networkidle")

        # Select the session checkbox
        session_checkbox = page.locator(
            f'input[name="_selected_action"][value="{session.id}"]'
        )
        session_checkbox.check()

        # Select "Form teams for this session" action
        action_select = page.locator('select[name="action"]')
        action_select.select_option(label="Form teams for this session")

        # Click "Go" button
        page.get_by_role("button", name="Go").click()
        page.wait_for_load_state("networkidle")

        # Verify we're on the team formation page
        expect(page.get_by_role("heading", level=1)).to_contain_text("Form Teams")

        # Assign djangonaut A to team
        djangonaut_a_checkbox = page.locator(
            f'.applicant-checkbox[value="{djangonaut_a.id}"]'
        )
        djangonaut_a_checkbox.check()

        # Select the team from the bulk assignment dropdown
        team_select = page.locator("#bulk-team-select")
        team_select.select_option(label=f"{team.name} - {project.name}")

        # Click assign button
        page.get_by_role("button", name="Assign to Team").click()
        page.wait_for_load_state("networkidle")

        # Verify success message
        expect(page.locator(".messagelist").first).to_contain_text(
            "Successfully assigned"
        )

    def _admin_adds_djangonaut_b_to_waitlist(
        self, page: Page, djangonaut_b: CustomUser
    ):
        """Admin adds djangonaut B to the waitlist."""
        # Add djangonaut B to waitlist
        djangonaut_b_checkbox = page.locator(
            f'.applicant-checkbox[value="{djangonaut_b.id}"]'
        )
        djangonaut_b_checkbox.check()

        # Click add to waitlist button
        page.get_by_role("button", name="Add to Waitlist").click()
        page.wait_for_load_state("networkidle")

        # Verify success message
        expect(page.locator(".messagelist").first).to_contain_text("Successfully added")

    def _admin_sends_session_result_notifications(self, page: Page, session: Session):
        """Admin sends session result notifications and logs out."""
        # Send session results notification
        page.goto("/django-admin/home/session/")
        page.wait_for_load_state("networkidle")

        # Select the session checkbox
        session_checkbox = page.locator(
            f'input[name="_selected_action"][value="{session.id}"]'
        )
        session_checkbox.check()

        # Select "Send session result notifications" action
        action_select = page.locator('select[name="action"]')
        action_select.select_option(label="Send session result notifications")

        # Click "Go" button
        page.get_by_role("button", name="Go").click()
        page.wait_for_load_state("networkidle")

        # Verify we're on the send results page
        expect(page.locator("h1")).to_contain_text("Send Session Result Notifications")

        # Fill in deadline days
        deadline_input = page.locator("#id_deadline_days")
        deadline_input.fill("7")

        # Clear mail outbox before sending
        mail.outbox.clear()

        # Submit the form
        page.get_by_role("button", name="Send Notifications").click()
        page.wait_for_load_state("networkidle")

        # Verify success message
        expect(page.locator(".messagelist")).to_contain_text("Successfully queued")

        # Logout admin
        self.logout(page)

    def _djangonaut_a_accepts_invitation(self, page: Page, session: Session):
        """Djangonaut A logs in, accepts invitation, and logs out."""
        # Login as djangonaut A
        page.goto(reverse("login"))
        page.locator("#id_username").fill("djangonaut_a")
        page.locator("#id_password").fill("testpass123")
        page.get_by_role("button", name="Login").click()
        page.wait_for_load_state("networkidle")

        # Navigate to acceptance page
        acceptance_url = reverse("accept_membership", kwargs={"slug": session.slug})
        page.goto(acceptance_url)
        page.wait_for_load_state("networkidle")

        # Accept the invitation
        page.get_by_role("button", name="Accept").click()
        page.wait_for_load_state("networkidle")

        # Verify acceptance message
        expect(page.locator("body")).to_contain_text("confirmed your participation")

        # Logout
        self.logout(page)

    def _djangonaut_b_accepts_invitation(self, page: Page, session: Session):
        """Djangonaut B logs in, accepts invitation, and logs out."""
        # Login as djangonaut B
        page.goto(reverse("login"))
        page.locator("#id_username").fill("djangonaut_b")
        page.locator("#id_password").fill("testpass123")
        page.get_by_role("button", name="Login").click()
        page.wait_for_load_state("networkidle")

        # Navigate to acceptance page
        acceptance_url = reverse("accept_membership", kwargs={"slug": session.slug})
        page.goto(acceptance_url)
        page.wait_for_load_state("networkidle")

        # Accept the invitation
        page.get_by_role("button", name="Accept").click()
        page.wait_for_load_state("networkidle")

        # Verify acceptance message
        expect(page.locator("body")).to_contain_text("confirmed your participation")

        # Logout
        self.logout(page)

    def _admin_promotes_djangonaut_b_from_waitlist_to_team(
        self,
        page: Page,
        superuser: CustomUser,
        session: Session,
        team: Team,
        project: Project,
        djangonaut_b: CustomUser,
    ):
        """Admin logs in, promotes djangonaut B from waitlist to team."""
        # Login as admin
        self.admin_login(page, superuser)

        # Navigate to team formation page
        team_formation_url = reverse(
            "admin:session_form_teams", kwargs={"session_id": session.id}
        )
        page.goto(team_formation_url)
        page.wait_for_load_state("networkidle")

        # Assign djangonaut B to team
        djangonaut_b_checkbox = page.locator(
            f'.applicant-checkbox[value="{djangonaut_b.id}"]'
        )
        djangonaut_b_checkbox.check()

        # Select the team from the bulk assignment dropdown
        team_select = page.locator("#bulk-team-select")
        team_select.select_option(label=f"{team.name} - {project.name}")

        # Click assign button
        page.get_by_role("button", name="Assign to Team").click()
        page.wait_for_load_state("networkidle")

        # Verify success message
        expect(page.locator(".messagelist").first).to_contain_text(
            "Successfully assigned"
        )

    def _admin_sends_acceptance_email_to_djangonaut_b(
        self,
        page: Page,
        session: Session,
        djangonaut_b: CustomUser,
    ):
        """Admin sends acceptance email to djangonaut B and logs out."""
        # Send acceptance emails to djangonaut B
        page.goto("/django-admin/home/sessionmembership/")
        page.wait_for_load_state("networkidle")

        # Find and select djangonaut B's membership
        membership_b = SessionMembership.objects.get(user=djangonaut_b, session=session)
        membership_checkbox = page.locator(
            f'input[name="_selected_action"][value="{membership_b.id}"]'
        )
        membership_checkbox.check()

        # Select "Send acceptance emails" action
        action_select = page.locator('select[name="action"]')
        action_select.select_option(label="Send acceptance emails to selected members")

        # Clear mail outbox
        mail.outbox.clear()

        # Click "Go" button
        page.get_by_role("button", name="Go").click()
        page.wait_for_load_state("networkidle")

        # Verify success message
        expect(page.locator(".messagelist")).to_contain_text("Successfully queued")

        # Logout admin
        self.logout(page)

    def _admin_send_team_welcome_emails(
        self, page: Page, superuser: CustomUser, session: Session
    ):
        """
        Admin sends team welcome emails.

        Admin logs in, sends team welcome emails to all accepted members, then logs out.
        """
        # Login as admin
        self.admin_login(page, superuser)

        # Navigate to session admin
        page.goto("/django-admin/home/session/")
        page.wait_for_load_state("networkidle")

        # Select the session checkbox
        session_checkbox = page.locator(
            f'input[name="_selected_action"][value="{session.id}"]'
        )
        session_checkbox.check()

        # Select "Send team welcome emails" action
        action_select = page.locator('select[name="action"]')
        action_select.select_option(label="Send team welcome emails")

        # Click "Go" button
        page.get_by_role("button", name="Go").click()
        page.wait_for_load_state("networkidle")

        # Verify we're on the send welcome emails page
        expect(page.locator("h1")).to_contain_text("Send Team Welcome Emails")

        # Clear mail outbox
        mail.outbox.clear()

        # Submit the form
        page.get_by_role("button", name="Send Welcome Emails").click()
        page.wait_for_load_state("networkidle")

        # Verify success message
        expect(page.locator(".messagelist")).to_contain_text("Successfully queued")

        # Logout admin
        self.logout(page)

    def _verify_all_team_members_can_access_team(
        self, page: Page, session: Session, team: Team, pause_at_end: bool
    ):
        """
        All team members verify they can access the team.

        Navigator, captain, djangonauts A & B, and organizer all log in,
        verify team access, and log out.
        """
        team_url = reverse(
            "team_detail",
            kwargs={"session_slug": session.slug, "pk": team.pk},
        )

        # Helper function to login and access team
        def verify_team_access(username: str, expected_members: list[str], logout=True):
            page.goto(reverse("login"))
            page.locator("#id_username").fill(username)
            page.locator("#id_password").fill("testpass123")
            page.get_by_role("button", name="Login").click()
            page.wait_for_load_state("networkidle")

            # Access My Sessions page
            page.goto(reverse("user_sessions"))
            page.wait_for_load_state("networkidle")
            expect(page.locator("body")).to_contain_text("Test Session 2024")

            # Access team detail page
            page.goto(team_url)
            page.wait_for_load_state("networkidle")

            # Verify team name is visible
            expect(page.locator("body")).to_contain_text("Team Alpha")

            # Verify expected members are visible
            for member in expected_members:
                expect(page.locator("body")).to_contain_text(member)

            if logout:
                self.logout(page)

        # Navigator verifies team access
        verify_team_access("navigator1", ["Django A", "Django B", "Cap One"])

        # Captain verifies team access
        verify_team_access("captain1", ["Django A", "Django B", "Nav One"])

        # Djangonaut A verifies team access
        verify_team_access("djangonaut_a", ["Nav One", "Cap One", "Django B"])

        # Djangonaut B verifies team access
        verify_team_access("djangonaut_b", ["Nav One", "Cap One", "Django A"])

        # Superuser (organizer) verifies team access
        # Don't logout if we're pausing so we can access the various pages as the super user
        verify_team_access(
            "admin",
            ["Django A", "Django B", "Nav One", "Cap One"],
            logout=not pause_at_end,
        )

    def _test_timezone_toggle_functionality(
        self, page: Page, session: Session, team: Team
    ):
        """
        Test the timezone toggle JavaScript functionality on team detail page.

        Verifies that:
        - Timezone toggle JavaScript is loaded
        - Toggle button exists and is clickable
        - HTMX is present and functional
        - Button text element is present
        - Individual member overlap times update when timezone is toggled
        """
        team_url = reverse(
            "team_detail",
            kwargs={"session_slug": session.slug, "pk": team.pk},
        )

        # Navigate to team detail page (should already be logged in as admin)
        page.goto(team_url)
        page.wait_for_load_state("networkidle")

        # Verify the timezone toggle JavaScript function exists
        toggle_function_exists = page.evaluate(
            "typeof window.toggleTimezone === 'function'"
        )
        assert toggle_function_exists, "toggleTimezone function should be defined"

        # Verify HTMX is loaded
        htmx_loaded = page.evaluate("typeof htmx !== 'undefined'")
        assert htmx_loaded, "HTMX should be loaded"

        # Wait for initial HTMX load to complete - availability section should always be present
        # since all test users have availability set
        page.wait_for_selector(
            "#team-availability-section", state="visible", timeout=5000
        )

        # Verify the toggle button exists
        toggle_button = page.get_by_role("button").filter(has_text="Show in")
        expect(toggle_button).to_be_visible()

        # Verify the button text element specifically
        button_text_span = page.locator("#toggle-button-text")
        expect(button_text_span).to_be_visible()

        # Get initial button text (strip whitespace for comparison)
        initial_button_text = button_text_span.text_content().strip()
        assert len(initial_button_text) > 0, "Button text should not be empty"

        # Verify the timezone display span exists
        timezone_span = page.locator("#team-availability-section span.font-bold")
        expect(timezone_span).to_be_visible()
        initial_timezone = timezone_span.text_content().strip()
        assert len(initial_timezone) > 0, "Timezone display should not be empty"

        # All test users have the same availability (Monday 9-10 AM UTC),
        # so there should be overlap sections showing
        overlap_times = page.locator(".member-overlap-times")
        assert (
            overlap_times.count() > 0
        ), "Should have overlap sections for team members"

        # Emulate browser timezone to Pacific/Kiritimati (UTC+14)
        # This is in the Line Islands, one of the easternmost timezones
        # and extremely unlikely to be anyone's actual timezone
        # This uses Chrome DevTools Protocol to set timezone
        cdp = page.context.new_cdp_session(page)
        cdp.send("Emulation.setTimezoneOverride", {"timezoneId": "Pacific/Kiritimati"})

        # Reload the page to pick up the new timezone
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_selector(
            "#team-availability-section", state="visible", timeout=5000
        )

        # Re-get the toggle button and spans after reload
        toggle_button = page.get_by_role("button").filter(has_text="Show in")
        button_text_span = page.locator("#toggle-button-text")
        timezone_span = page.locator("#team-availability-section span.font-bold")

        # Get the timezone after reload (should now be Pacific/Kiritimati)
        initial_timezone_local = timezone_span.text_content().strip()
        assert (
            "Pacific/Kiritimati" in initial_timezone_local
        ), f"Expected timezone to be Pacific/Kiritimati, got: {initial_timezone_local}"

        # Get initial overlap times in Pacific/Kiritimati timezone
        # 9 AM UTC = 11 PM Pacific/Kiritimati (previous day due to +14 offset)
        overlap_times = page.locator(".member-overlap-times")
        initial_overlap_times_local = overlap_times.first.inner_text()

        # Click the toggle button to switch to UTC
        toggle_button.click()

        # Wait for any HTMX requests to complete
        page.wait_for_load_state("networkidle")

        # Wait for the availability section to be re-rendered after HTMX swap
        page.wait_for_selector("#team-availability-section", state="attached")

        # Verify button is still visible after click (ensures page didn't error)
        expect(toggle_button).to_be_visible()
        expect(button_text_span).to_be_visible()

        # Get the updated timezone display
        updated_timezone = timezone_span.text_content().strip()
        assert (
            updated_timezone == "UTC"
        ), f"After toggle, timezone should be UTC, got: {updated_timezone}"

        # Check if individual member overlap times updated
        # Re-query the overlap sections after the toggle
        updated_overlap_times = page.locator(".member-overlap-times")
        assert (
            updated_overlap_times.count() > 0
        ), "Should still have overlap sections after toggle"

        updated_overlap_times_utc = updated_overlap_times.first.inner_text()

        # The times MUST be different after switching from Pacific/Kiritimati to UTC
        # With a 14-hour offset, times will definitely be different
        # This will catch the bug where member cards don't update
        assert initial_overlap_times_local != updated_overlap_times_utc, (
            "Individual member overlap times MUST update when timezone changes "
            f"from {initial_timezone_local} to {updated_timezone}. "
            f"Local TZ times: {initial_overlap_times_local!r},"
            f"UTC times: {updated_overlap_times_utc!r}. "
            "This indicates the member cards are not being re-rendered on timezone toggle."
        )

    @patch("django_recaptcha.fields.ReCaptchaField.validate", return_value=True)
    def test_complete_session_onboarding_flow(
        self, mock_captcha, page: Page, db, pause_at_end
    ):
        """
        Complete end-to-end test for the session flow.

        Tests the entire workflow from user signup to team member access.

        Use --pause-at-end flag to pause at the end for manual exploration:
            uv run pytest -m playwright -k 'test_complete_session_onboarding_flow' \
                --headed --pause-at-end
        """
        # ======================================================================
        # PHASE 1: Navigator and Captain onboard
        # ======================================================================

        navigator = self._navigator_signs_up_and_sets_availability(page)
        captain = self._captain_signs_up_and_sets_availability(page)

        # ======================================================================
        # PHASE 2: Admin sets up session structure
        # ======================================================================

        superuser, session = self._admin_creates_session(page)
        survey = self._admin_creates_application_survey(page, session)
        project, team = self._admin_creates_project_and_team(page, session)
        self._admin_adds_navigator_and_captain_to_team(
            page, session, team, navigator, captain
        )
        self._admin_adds_themselves_as_organizer(page, superuser, session)

        # ======================================================================
        # PHASE 3: Djangonauts apply to session
        # ======================================================================

        djangonaut_a = self._djangonaut_a_applies_to_session(page, survey)
        djangonaut_b = self._djangonaut_b_applies_to_session(page, survey)
        djangonaut_c = self._djangonaut_c_applies_to_session(page, survey)

        # ======================================================================
        # PHASE 4: Admin forms teams and sends notifications
        # ======================================================================

        self._admin_assigns_djangonaut_a_to_team(
            page, superuser, session, team, project, djangonaut_a
        )
        self._admin_adds_djangonaut_b_to_waitlist(page, djangonaut_b)
        self._admin_sends_session_result_notifications(page, session)

        self._djangonaut_a_accepts_invitation(page, session)

        self._admin_promotes_djangonaut_b_from_waitlist_to_team(
            page, superuser, session, team, project, djangonaut_b
        )
        self._admin_sends_acceptance_email_to_djangonaut_b(page, session, djangonaut_b)

        self._djangonaut_b_accepts_invitation(page, session)

        self._admin_send_team_welcome_emails(page, superuser, session)

        # ======================================================================
        # PHASE 5: Team members verify access
        # ======================================================================

        self._verify_all_team_members_can_access_team(page, session, team, False)

        # ======================================================================
        # PHASE 6: Test timezone toggle JavaScript functionality
        # ======================================================================

        # Login as navigator (who has availability and overlaps with team members)
        page.goto(reverse("login"))
        page.locator("#id_username").fill("navigator1")
        page.locator("#id_password").fill("testpass123")
        page.get_by_role("button", name="Login").click()
        page.wait_for_load_state("networkidle")

        self._test_timezone_toggle_functionality(page, session, team)

        # Optional: Pause for manual exploration
        # ======================================================================
        if pause_at_end:
            print("\n" + "=" * 70)
            print("TEST COMPLETE - Browser paused for manual exploration")
            print("=" * 70)
            print("\nYou can now manually explore the application state.")
            print("\nAvailable test accounts (all use password: testpass123):")
            print("  - navigator1 (Navigator on Team Alpha)")
            print("  - captain1 (Captain on Team Alpha)")
            print("  - djangonaut_a (Djangonaut on Team Alpha)")
            print("  - djangonaut_b (Djangonaut on Team Alpha)")
            print("  - djangonaut_c (Not assigned to any team)")
            print("  - admin (Superuser/Organizer)")
            page.pause()
