from io import StringIO

import pytest
from django.core import mail, management

from accounts.factories import UserFactory


@pytest.mark.django_db
class TestNotifyUnusablePasswordUsersCommand:

    @pytest.fixture(autouse=True)
    def settings(self, settings):
        settings.ENVIRONMENT = "production"
        return settings

    def test_sends_expected_email_to_unusable_password_user(self):
        user = UserFactory.create(is_active=True)
        user.set_unusable_password()
        user.save()

        management.call_command("notify_unusable_password_users", stdout=StringIO())

        assert len(mail.outbox) == 1
        email = mail.outbox[0]
        assert email.to == [user.email]
        assert email.subject == "A Djangonaut Space account has been created for you"
        assert "/accounts/reset/" in email.body
        assert "delete" in email.body

    def test_skips_users_with_usable_passwords(self):
        user = UserFactory.create(is_active=True)
        user.set_password("strongpassword123")
        user.save()

        management.call_command("notify_unusable_password_users", stdout=StringIO())

        assert len(mail.outbox) == 0

    def test_skips_inactive_users(self):
        user = UserFactory.create(is_active=False)
        user.set_unusable_password()
        user.save()

        management.call_command("notify_unusable_password_users", stdout=StringIO())

        assert len(mail.outbox) == 0

    def test_sends_to_multiple_unusable_password_users(self):
        for _ in range(3):
            user = UserFactory.create(is_active=True)
            user.set_unusable_password()
            user.save()

        management.call_command("notify_unusable_password_users", stdout=StringIO())

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
