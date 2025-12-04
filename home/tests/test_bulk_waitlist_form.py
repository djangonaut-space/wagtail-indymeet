"""Tests for BulkWaitlistForm and waitlist functionality."""

from django.test import TestCase

from accounts.factories import UserFactory
from home.factories import SessionFactory, SurveyFactory
from home.forms import BulkWaitlistForm
from home.models import SessionMembership, UserSurveyResponse, Waitlist


class BulkWaitlistFormTestCase(TestCase):
    """Test BulkWaitlistForm validation and saving."""

    @classmethod
    def setUpTestData(cls):
        """Create test data."""
        cls.session = SessionFactory()
        cls.survey = SurveyFactory(session=cls.session)
        cls.session.application_survey = cls.survey
        cls.session.save()

        # Create users
        cls.user1 = UserFactory(username="user1")
        cls.user2 = UserFactory(username="user2")
        cls.user3 = UserFactory(username="user3")

        # Create survey responses
        UserSurveyResponse.objects.create(user=cls.user1, survey=cls.survey)
        UserSurveyResponse.objects.create(user=cls.user2, survey=cls.survey)
        UserSurveyResponse.objects.create(user=cls.user3, survey=cls.survey)

    def test_valid_waitlist_addition(self):
        """Test that valid users can be added to waitlist."""
        form = BulkWaitlistForm(
            data={
                "bulk_waitlist-user_ids": f"{self.user1.id},{self.user2.id}",
            },
            session=self.session,
        )

        self.assertTrue(form.is_valid(), form.errors)

        # Save and verify
        count = form.save()
        self.assertEqual(count, 2)

        # Verify database entries
        self.assertTrue(
            Waitlist.objects.filter(user=self.user1, session=self.session).exists()
        )
        self.assertTrue(
            Waitlist.objects.filter(user=self.user2, session=self.session).exists()
        )

    def test_nonexistent_user_ids(self):
        """Test validation when user IDs don't exist."""
        form = BulkWaitlistForm(
            data={
                "bulk_waitlist-user_ids": "99999,88888",
            },
            session=self.session,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("user_ids", form.errors)
        self.assertIn("do not exist", form.errors["user_ids"][0])

    def test_cannot_waitlist_existing_session_member(self):
        """Test that users who are already session members cannot be waitlisted."""
        # Make user1 a session member
        SessionMembership.objects.create(
            user=self.user1, session=self.session, role=SessionMembership.DJANGONAUT
        )

        form = BulkWaitlistForm(
            data={
                "bulk_waitlist-user_ids": f"{self.user1.id}",
            },
            session=self.session,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)
        error_message = form.errors["__all__"][0]
        self.assertIn(self.user1.get_full_name(), error_message)
        self.assertIn("already session members", error_message)

    def test_mixed_valid_and_invalid_users(self):
        """Test validation when some users are session members (invalid)."""
        # Make user1 a session member
        SessionMembership.objects.create(
            user=self.user1, session=self.session, role=SessionMembership.DJANGONAUT
        )

        # User2 is already on waitlist (valid - idempotent operation)
        Waitlist.objects.create(user=self.user2, session=self.session)

        form = BulkWaitlistForm(
            data={
                "bulk_waitlist-user_ids": f"{self.user1.id},{self.user2.id},{self.user3.id}",
            },
            session=self.session,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("__all__", form.errors)

        # Only error for session members, not for already waitlisted
        error_messages = "".join(form.errors["__all__"])
        self.assertIn(self.user1.get_full_name(), error_messages)
        self.assertIn("already session members", error_messages)
