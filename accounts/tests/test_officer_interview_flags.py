"""
Tests for the admin-only officer interview flags on UserProfile.
"""

from django.test import TestCase
from django.urls import reverse

from accounts.factories import UserFactory
from home import constants


class UserProfileInterviewFlagTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()

    def test_flags_default_to_not_interviewed(self):
        profile = self.user.profile

        self.assertIsNone(profile.passed_captain_interview)
        self.assertIsNone(profile.passed_navigator_interview)
        self.assertFalse(profile.had_interview(constants.CAPTAIN))
        self.assertFalse(profile.had_interview(constants.NAVIGATOR))

    def test_had_interview_is_true_whether_passed_or_not(self):
        profile = self.user.profile
        profile.passed_captain_interview = True
        profile.passed_navigator_interview = False

        self.assertTrue(profile.had_interview(constants.CAPTAIN))
        self.assertTrue(profile.had_interview(constants.NAVIGATOR))


class UserProfileInterviewAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = UserFactory.create(
            username="admin", is_staff=True, is_superuser=True
        )
        cls.user = UserFactory.create(username="volunteer")
        cls.other_user = UserFactory.create(username="other")
        cls.changelist_url = reverse("admin:accounts_userprofile_changelist")

    def setUp(self):
        self.client.force_login(self.admin_user)

    def test_change_form_includes_interview_flags(self):
        url = reverse("admin:accounts_userprofile_change", args=[self.user.profile.pk])

        response = self.client.get(url)

        self.assertContains(response, "passed_captain_interview")
        self.assertContains(response, "passed_navigator_interview")

    def test_changelist_filters_by_interview_flag(self):
        self.user.profile.passed_captain_interview = True
        self.user.profile.save(update_fields=["passed_captain_interview"])

        response = self.client.get(
            self.changelist_url, {"passed_captain_interview__exact": "1"}
        )

        self.assertEqual(list(response.context["cl"].result_list), [self.user.profile])

    def test_record_interview_actions(self):
        cases = [
            ("mark_passed_captain_interview", "passed_captain_interview", True),
            ("mark_failed_captain_interview", "passed_captain_interview", False),
            ("mark_passed_navigator_interview", "passed_navigator_interview", True),
            ("mark_failed_navigator_interview", "passed_navigator_interview", False),
        ]
        for action, field, expected in cases:
            with self.subTest(action=action):
                response = self.client.post(
                    self.changelist_url,
                    {"action": action, "_selected_action": [self.user.profile.pk]},
                    follow=True,
                )

                self.assertEqual(response.status_code, 200)
                self.user.profile.refresh_from_db()
                self.other_user.profile.refresh_from_db()
                self.assertIs(getattr(self.user.profile, field), expected)
                self.assertIsNone(getattr(self.other_user.profile, field))


class InterviewFlagsHiddenFromUsersTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create()
        cls.update_account_url = reverse("update_user")

    def setUp(self):
        self.client.force_login(self.user)

    def test_update_account_page_does_not_show_flags(self):
        response = self.client.get(self.update_account_url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "passed_captain_interview")
        self.assertNotContains(response, "passed_navigator_interview")

    def test_user_cannot_set_flags_when_updating_account(self):
        self.client.post(
            self.update_account_url,
            data={
                "username": self.user.username,
                "email": self.user.email,
                "first_name": "Jane",
                "last_name": "Doe",
                "passed_captain_interview": True,
                "passed_navigator_interview": True,
            },
        )

        self.user.profile.refresh_from_db()
        self.assertIsNone(self.user.profile.passed_captain_interview)
        self.assertIsNone(self.user.profile.passed_navigator_interview)
