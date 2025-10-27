from django.core import mail
from django.test import TestCase, override_settings

from accounts.factories import UserFactory
from home import email


class EmailSendTests(TestCase):
    """Tests for the home.email.send function"""

    @classmethod
    def setUpTestData(cls):
        cls.user = UserFactory.create(
            email="test@example.com",
            first_name="Test",
        )

    @override_settings(
        ENVIRONMENT="production",
        DEFAULT_FROM_EMAIL="noreply@djangonaut.space",
    )
    def test_send_email_in_production(self):
        """Test that emails are sent to all recipients in production"""
        context = {"user": self.user}
        email.send(
            email_template="application_created",
            recipient_list=["test@example.com", "another@example.com"],
            context=context,
        )

        # Check that 1 email was sent (send_mail sends one email to multiple recipients)
        self.assertEqual(len(mail.outbox), 1)

        # Check recipients
        recipients = mail.outbox[0].recipients()
        self.assertIn("test@example.com", recipients)
        self.assertIn("another@example.com", recipients)

        # Check subject (no environment prefix in production)
        self.assertEqual(
            mail.outbox[0].subject,
            "Djangonaut Space Application Submitted",
        )

        # Check from email
        self.assertEqual(
            mail.outbox[0].from_email,
            "noreply@djangonaut.space",
        )

    @override_settings(ENVIRONMENT="production")
    def test_send_email_with_custom_from_email(self):
        """Test that custom from_email is used when provided"""
        context = {"user": self.user}
        email.send(
            email_template="application_created",
            recipient_list=["test@example.com"],
            context=context,
            from_email="custom@djangonaut.space",
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].from_email, "custom@djangonaut.space")

    @override_settings(
        ENVIRONMENT="dev",
        ALLOWED_EMAILS_FOR_TESTING=["allowed@example.com"],
    )
    def test_send_email_in_dev_with_allowed_recipients(self):
        """Test that emails are filtered to allowed recipients in dev"""
        context = {"user": self.user}
        email.send(
            email_template="application_created",
            recipient_list=[
                "allowed@example.com",
                "notallowed@example.com",
            ],
            context=context,
        )

        # Only one email should be sent (to allowed recipient)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].recipients(), ["allowed@example.com"])

        # Check subject has environment prefix
        self.assertEqual(
            mail.outbox[0].subject,
            "[dev] Djangonaut Space Application Submitted",
        )

    @override_settings(
        ENVIRONMENT="dev",
        ALLOWED_EMAILS_FOR_TESTING=["allowed@example.com"],
    )
    def test_send_email_in_dev_with_no_allowed_recipients(self):
        """Test that no emails are sent if no recipients are allowed in dev"""
        context = {"user": self.user}
        email.send(
            email_template="application_created",
            recipient_list=["notallowed@example.com"],
            context=context,
        )

        # No emails should be sent
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(
        ENVIRONMENT="staging",
        ALLOWED_EMAILS_FOR_TESTING=["test@example.com"],
    )
    def test_send_email_with_staging_environment(self):
        """Test that staging environment prefix is added to subject"""
        context = {"user": self.user}
        email.send(
            email_template="application_created",
            recipient_list=["test@example.com"],
            context=context,
        )

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(
            mail.outbox[0].subject,
            "[staging] Djangonaut Space Application Submitted",
        )

    @override_settings(
        ENVIRONMENT="dev",
        ALLOWED_EMAILS_FOR_TESTING=[],
    )
    def test_send_email_handles_empty_recipient_list(self):
        """Test that sending with empty recipient list doesn't crash"""
        context = {"user": self.user}
        # This should not raise an exception
        email.send(
            email_template="application_created",
            recipient_list=["test@example.com"],
            context=context,
        )

        # No emails should be sent
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(ENVIRONMENT="production")
    def test_send_email_with_empty_context(self):
        """Test that send handles empty context"""
        # When context is empty dict, it should work fine
        email.send(
            email_template="application_created",
            recipient_list=["test@example.com"],
            context={},
        )
        # Should send email successfully
        self.assertEqual(len(mail.outbox), 1)
