"""
Tests for the captain and navigator application flow.

Covers the Survey role field, the officer result notification tasks, and the
admin view that sends each role's results separately.
"""

from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.core import mail
from django.db import IntegrityError
from django.test import RequestFactory, TestCase, override_settings
from django.urls import reverse

from accounts.factories import UserFactory
from home import constants
from home.admin import SurveyAdmin
from home.factories import (
    SessionFactory,
    SessionMembershipFactory,
    SurveyFactory,
    UserSurveyResponseFactory,
)
from home.models import Survey
from home.tasks.session_notifications import (
    send_officer_accepted_email,
    send_officer_rejected_email,
)


class SurveyRoleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create()

    def test_role_defaults_to_none(self):
        survey = SurveyFactory.create(session=self.session)

        self.assertIsNone(survey.role)

    def test_for_role_returns_session_role_survey(self):
        navigator_survey = SurveyFactory.create(
            session=self.session, role=constants.NAVIGATOR
        )
        SurveyFactory.create(session=self.session, role=constants.CAPTAIN)
        SurveyFactory.create(session=self.session)
        SurveyFactory.create(session=SessionFactory.create(), role=constants.NAVIGATOR)

        self.assertQuerySetEqual(
            Survey.objects.for_role(self.session, constants.NAVIGATOR),
            [navigator_survey],
        )

    def test_session_allows_many_surveys_without_role(self):
        SurveyFactory.create(session=self.session)
        SurveyFactory.create(session=self.session)

        self.assertEqual(Survey.objects.filter(session=self.session).count(), 2)

    def test_session_allows_one_survey_per_role(self):
        SurveyFactory.create(session=self.session, role=constants.CAPTAIN)

        with self.assertRaises(IntegrityError):
            SurveyFactory.create(session=self.session, role=constants.CAPTAIN)

    def test_copy_survey_keeps_role_and_detaches_session(self):
        survey = SurveyFactory.create(session=self.session, role=constants.CAPTAIN)
        admin_user = UserFactory.create(is_staff=True, is_superuser=True)
        request = RequestFactory().post("/")
        request.user = admin_user
        model_admin = SurveyAdmin(Survey, AdminSite())

        with patch.object(model_admin, "message_user"):
            model_admin.copy_survey(request, Survey.objects.filter(pk=survey.pk))

        copy = Survey.objects.exclude(pk=survey.pk).get()
        self.assertEqual(copy.role, constants.CAPTAIN)
        self.assertIsNone(copy.session)


class SendOfficerAcceptedEmailTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create(title="Test Session")
        cls.user = UserFactory.create(email="nav@example.com", first_name="Nia")
        cls.membership = SessionMembershipFactory.create(
            session=cls.session, user=cls.user, role=constants.NAVIGATOR, team=None
        )

    @patch("home.tasks.session_notifications.email.send")
    def test_sends_officer_accepted_email(self, mock_send):
        send_officer_accepted_email.call(membership_id=self.membership.pk)

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        self.assertEqual(call_kwargs["email_template"], "officer_accepted")
        self.assertEqual(call_kwargs["recipient_list"], ["nav@example.com"])
        self.assertEqual(call_kwargs["context"]["role"], "Navigator")
        self.assertEqual(call_kwargs["context"]["name"], "Nia")
        self.assertEqual(call_kwargs["context"]["session"], self.session)

    @override_settings(ENVIRONMENT="production")
    def test_renders_officer_accepted_email(self):
        send_officer_accepted_email.call(membership_id=self.membership.pk)

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Navigator", mail.outbox[0].subject)
        self.assertIn("Test Session", mail.outbox[0].body)


class SendOfficerRejectedEmailTaskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create(title="Test Session")
        cls.user = UserFactory.create(email="cap@example.com", first_name="Cal")

    @patch("home.tasks.session_notifications.email.send")
    def test_sends_template_for_interview_status(self, mock_send):
        cases = [(True, "officer_rejected_interviewed"), (False, "officer_rejected")]
        for interviewed, template in cases:
            with self.subTest(interviewed=interviewed):
                mock_send.reset_mock()

                send_officer_rejected_email.call(
                    user_id=self.user.pk,
                    session_id=self.session.pk,
                    role=constants.CAPTAIN,
                    interviewed=interviewed,
                )

                call_kwargs = mock_send.call_args.kwargs
                self.assertEqual(call_kwargs["email_template"], template)
                self.assertEqual(call_kwargs["recipient_list"], ["cap@example.com"])
                self.assertEqual(call_kwargs["context"]["role"], constants.CAPTAIN)

    @override_settings(ENVIRONMENT="production")
    def test_renders_interviewed_rejection_email(self):
        send_officer_rejected_email.call(
            user_id=self.user.pk,
            session_id=self.session.pk,
            role=constants.CAPTAIN,
            interviewed=True,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Captain", mail.outbox[0].subject)
        self.assertIn("interview", mail.outbox[0].body)


@patch("home.views.session_notifications.tasks.send_officer_rejected_email")
@patch("home.views.session_notifications.tasks.send_officer_accepted_email")
class SendOfficerResultsViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.djangonaut_survey = SurveyFactory.create(name="Djangonaut Application")
        cls.session = SessionFactory.create(
            title="Test Session", application_survey=cls.djangonaut_survey
        )
        cls.djangonaut_survey.session = cls.session
        cls.djangonaut_survey.save()
        cls.navigator_survey = SurveyFactory.create(
            name="Navigator Application",
            session=cls.session,
            role=constants.NAVIGATOR,
        )

        cls.selected = UserFactory.create(email="selected@example.com")
        cls.interviewed = UserFactory.create(
            email="interviewed@example.com",
            profile__passed_navigator_interview=False,
        )
        cls.captain_interviewed_only = UserFactory.create(
            email="captain-interviewed@example.com",
            profile__passed_captain_interview=True,
        )
        cls.not_interviewed = UserFactory.create(email="not-interviewed@example.com")
        cls.made_captain = UserFactory.create(email="made-captain@example.com")
        cls.djangonaut = UserFactory.create(email="djangonaut@example.com")

        for user in (
            cls.selected,
            cls.interviewed,
            cls.captain_interviewed_only,
            cls.not_interviewed,
            cls.made_captain,
        ):
            UserSurveyResponseFactory.create(user=user, survey=cls.navigator_survey)
        UserSurveyResponseFactory.create(
            user=cls.djangonaut, survey=cls.djangonaut_survey
        )

        cls.selected_membership = SessionMembershipFactory.create(
            session=cls.session, user=cls.selected, role=constants.NAVIGATOR, team=None
        )
        SessionMembershipFactory.create(
            session=cls.session,
            user=cls.made_captain,
            role=constants.CAPTAIN,
            team=None,
        )
        SessionMembershipFactory.create(
            session=cls.session,
            user=cls.djangonaut,
            role=constants.DJANGONAUT,
            team=None,
        )

        cls.admin_user = UserFactory.create(is_staff=True, is_superuser=True)
        cls.url = reverse(
            "admin:session_send_officer_results", args=[cls.session.pk, "navigator"]
        )

    def setUp(self):
        self.client.force_login(self.admin_user)

    def rejected_calls(self, mock_rejected) -> dict[int, dict]:
        return {
            call.kwargs["user_id"]: call.kwargs
            for call in mock_rejected.enqueue.call_args_list
        }

    def test_get_shows_groups(self, mock_accepted, mock_rejected):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.context["selected_memberships"], [self.selected_membership]
        )
        self.assertEqual(response.context["interviewed_users"], [self.interviewed])
        self.assertCountEqual(
            response.context["not_interviewed_users"],
            [self.captain_interviewed_only, self.not_interviewed],
        )
        self.assertNotContains(response, "made-captain@example.com")
        self.assertNotContains(response, "djangonaut@example.com")
        self.assertNotContains(response, "confirm_resend")
        mock_accepted.enqueue.assert_not_called()
        mock_rejected.enqueue.assert_not_called()

    def test_post_enqueues_emails_by_interview_status(
        self, mock_accepted, mock_rejected
    ):
        response = self.client.post(self.url, {"send_interviewed_rejection": "on"})

        self.assertRedirects(response, reverse("admin:home_session_changelist"))
        mock_accepted.enqueue.assert_called_once_with(
            membership_id=self.selected_membership.pk
        )
        rejected = self.rejected_calls(mock_rejected)
        self.assertEqual(
            set(rejected),
            {
                self.interviewed.pk,
                self.captain_interviewed_only.pk,
                self.not_interviewed.pk,
            },
        )
        self.assertTrue(rejected[self.interviewed.pk]["interviewed"])
        self.assertFalse(rejected[self.captain_interviewed_only.pk]["interviewed"])
        self.assertFalse(rejected[self.not_interviewed.pk]["interviewed"])
        self.assertEqual(rejected[self.interviewed.pk]["role"], constants.NAVIGATOR)
        self.session.refresh_from_db()
        self.assertIsNotNone(self.session.navigator_results_notifications_sent_at)
        self.assertIsNone(self.session.captain_results_notifications_sent_at)
        self.assertIsNone(self.session.results_notifications_sent_at)

    def test_post_without_interviewed_rejection_sends_standard_email(
        self, mock_accepted, mock_rejected
    ):
        self.client.post(self.url, {})

        rejected = self.rejected_calls(mock_rejected)
        self.assertEqual(len(rejected), 3)
        self.assertFalse(any(kwargs["interviewed"] for kwargs in rejected.values()))

    def test_resend_requires_confirmation(self, mock_accepted, mock_rejected):
        self.client.post(self.url, {"send_interviewed_rejection": "on"})
        self.session.refresh_from_db()
        first_sent_at = self.session.navigator_results_notifications_sent_at
        mock_accepted.reset_mock()
        mock_rejected.reset_mock()

        response = self.client.post(self.url, {"send_interviewed_rejection": "on"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "already sent")
        mock_accepted.enqueue.assert_not_called()
        mock_rejected.enqueue.assert_not_called()
        self.session.refresh_from_db()
        self.assertEqual(
            self.session.navigator_results_notifications_sent_at, first_sent_at
        )

        response = self.client.post(
            self.url, {"send_interviewed_rejection": "on", "confirm_resend": "on"}
        )

        self.assertRedirects(response, reverse("admin:home_session_changelist"))
        mock_accepted.enqueue.assert_called_once()
        self.assertEqual(mock_rejected.enqueue.call_count, 3)

    def test_roles_have_independent_sent_guards(self, mock_accepted, mock_rejected):
        SurveyFactory.create(session=self.session, role=constants.CAPTAIN)
        self.client.post(self.url, {})
        captain_url = reverse(
            "admin:session_send_officer_results", args=[self.session.pk, "captain"]
        )

        response = self.client.get(captain_url)

        self.assertFalse(response.context["already_sent"])
        self.assertNotContains(response, "confirm_resend")

    def test_missing_role_survey_redirects_with_error(
        self, mock_accepted, mock_rejected
    ):
        url = reverse(
            "admin:session_send_officer_results", args=[self.session.pk, "captain"]
        )

        response = self.client.get(url, follow=True)

        self.assertRedirects(response, reverse("admin:home_session_changelist"))
        self.assertContains(response, "has no Captain application survey")

    def test_unknown_role_returns_404(self, mock_accepted, mock_rejected):
        for role_slug in ("djangonaut", "organizer", "pilot"):
            with self.subTest(role_slug=role_slug):
                url = reverse(
                    "admin:session_send_officer_results",
                    args=[self.session.pk, role_slug],
                )

                response = self.client.get(url)

                self.assertEqual(response.status_code, 404)

    def test_session_changelist_links_to_officer_results(
        self, mock_accepted, mock_rejected
    ):
        response = self.client.get(reverse("admin:home_session_changelist"))

        self.assertContains(response, self.url)
        self.assertContains(response, "Send captain results")

    @patch("home.views.session_notifications.tasks.send_rejected_email")
    @patch("home.views.session_notifications.tasks.send_waitlisted_email")
    @patch("home.views.session_notifications.tasks.send_accepted_email")
    def test_djangonaut_results_ignore_officer_applicants(
        self,
        mock_djangonaut_accepted,
        mock_waitlisted,
        mock_djangonaut_rejected,
        mock_accepted,
        mock_rejected,
    ):
        url = reverse("admin:session_send_results", args=[self.session.pk])

        self.client.post(url, {"deadline_days": "7"})

        mock_djangonaut_accepted.enqueue.assert_called_once()
        mock_djangonaut_rejected.enqueue.assert_not_called()
        mock_accepted.enqueue.assert_not_called()
        mock_rejected.enqueue.assert_not_called()
