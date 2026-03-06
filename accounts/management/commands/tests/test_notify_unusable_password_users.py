import pytest
from django.core import mail, management
from django.contrib.auth import get_user_model

from accounts.factories import UserFactory

User = get_user_model()


@pytest.mark.django_db
class TestNotifyUnusablePasswordUsersCommand:
    def test_sends_email_to_unusable_password_user(self):
        user = UserFactory.create(is_active=True)
        user.set_unusable_password()
        user.save()

        management.call_command("notify_unusable_password_users")

        assert len(mail.outbox) == 1
        assert mail.outbox[0].to == [user.email]

    def test_email_subject(self):
        user = UserFactory.create(is_active=True)
        user.set_unusable_password()
        user.save()

        management.call_command("notify_unusable_password_users")

        assert len(mail.outbox) == 1
        assert (
            mail.outbox[0].subject
            == "A Djangonaut Space account has been created for you"
        )

    def test_email_contains_password_reset_link(self):
        user = UserFactory.create(is_active=True)
        user.set_unusable_password()
        user.save()

        management.call_command("notify_unusable_password_users")

        assert len(mail.outbox) == 1
        assert "/accounts/reset/" in mail.outbox[0].body

    def test_email_contains_delete_account_url(self):
        user = UserFactory.create(is_active=True)
        user.set_unusable_password()
        user.save()

        management.call_command("notify_unusable_password_users")

        assert len(mail.outbox) == 1
        assert "delete" in mail.outbox[0].body

    def test_skips_users_with_usable_passwords(self):
        user = UserFactory.create(is_active=True)
        user.set_password("strongpassword123")
        user.save()

        management.call_command("notify_unusable_password_users")

        assert len(mail.outbox) == 0

    def test_skips_inactive_users(self):
        user = UserFactory.create(is_active=False)
        user.set_unusable_password()
        user.save()

        management.call_command("notify_unusable_password_users")

        assert len(mail.outbox) == 0

    def test_sends_to_multiple_unusable_password_users(self):
        for _ in range(3):
            user = UserFactory.create(is_active=True)
            user.set_unusable_password()
            user.save()

        management.call_command("notify_unusable_password_users")

        assert len(mail.outbox) == 3

    def test_dry_run_does_not_send_emails(self, capsys):
        user = UserFactory.create(is_active=True)
        user.set_unusable_password()
        user.save()

        management.call_command("notify_unusable_password_users", dry_run=True)

        assert len(mail.outbox) == 0
        captured = capsys.readouterr()
        assert user.email in captured.out
        assert "1 user(s) would be notified" in captured.out
