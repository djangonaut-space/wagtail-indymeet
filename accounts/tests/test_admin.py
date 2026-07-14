from home import constants
from datetime import timedelta
from http import HTTPStatus
from unittest.mock import MagicMock, patch

from django.contrib import admin
from django.contrib.auth.models import Group
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.admin import CustomUserAdmin
from accounts.factories import UserAvailabilityFactory, UserFactory
from accounts.models import CustomUser, UserProfile
from home.factories import SessionFactory, SessionMembershipFactory


class AdminFilterTests(TestCase):

    @classmethod
    def setUpTestData(cls) -> None:
        cls.superuser = CustomUser.objects.create_superuser(
            username="admin", email="admin@example.com", password="test"
        )
        today = timezone.now().date()
        past_session = SessionFactory.create(
            start_date=today - timedelta(days=90),
            end_date=today - timedelta(days=30),
        )
        future_session = SessionFactory.create(
            start_date=today + timedelta(days=30),
            end_date=today + timedelta(days=90),
        )

        cls.past_djangonaut = UserFactory.create(username="past_djangonaut")
        SessionMembershipFactory.create(
            user=cls.past_djangonaut,
            session=past_session,
            role=constants.DJANGONAUT,
            team=None,
        )

        cls.past_navigator = UserFactory.create(username="past_navigator")
        SessionMembershipFactory.create(
            user=cls.past_navigator,
            session=past_session,
            role=constants.NAVIGATOR,
            team=None,
        )

        cls.future_djangonaut = UserFactory.create(username="future_djangonaut")
        SessionMembershipFactory.create(
            user=cls.future_djangonaut,
            session=future_session,
            role=constants.DJANGONAUT,
            team=None,
        )

        cls.no_session_user = UserFactory.create(username="no_session")

        UserAvailabilityFactory.create(user=cls.past_djangonaut)
        UserAvailabilityFactory.create(user=cls.no_session_user)

    def setUp(self) -> None:
        self.client.force_login(self.superuser)

    def _get_filtered_values(
        self, url: str, params: dict, field: str = "username"
    ) -> set:
        response = self.client.get(url, params)
        assert response.status_code == HTTPStatus.OK
        return set(response.context["cl"].queryset.values_list(field, flat=True))

    def test_customuser_past_djangonaut_yes(self) -> None:
        url = reverse("admin:accounts_customuser_changelist")
        users = self._get_filtered_values(url, {"past_djangonaut": "yes"})
        assert "past_djangonaut" in users
        assert "future_djangonaut" in users
        assert "past_navigator" not in users

    def test_customuser_past_djangonaut_no(self) -> None:
        url = reverse("admin:accounts_customuser_changelist")
        users = self._get_filtered_values(url, {"past_djangonaut": "no"})
        assert "past_djangonaut" not in users
        assert "past_navigator" in users
        assert "no_session" in users

    def test_customuser_past_session_member_yes(self) -> None:
        url = reverse("admin:accounts_customuser_changelist")
        users = self._get_filtered_values(url, {"past_session_member": "yes"})
        assert "past_djangonaut" in users
        assert "past_navigator" in users
        assert "future_djangonaut" in users
        assert "no_session" not in users

    def test_customuser_past_session_member_no(self) -> None:
        url = reverse("admin:accounts_customuser_changelist")
        users = self._get_filtered_values(url, {"past_session_member": "no"})
        assert "past_djangonaut" not in users
        assert "past_navigator" not in users
        assert "no_session" in users

    def test_userprofile_past_djangonaut_yes(self) -> None:
        url = reverse("admin:accounts_userprofile_changelist")
        user_ids = self._get_filtered_values(
            url, {"past_djangonaut": "yes"}, field="user_id"
        )
        assert self.past_djangonaut.pk in user_ids
        assert self.past_navigator.pk not in user_ids

    def test_userprofile_past_session_member_yes(self) -> None:
        url = reverse("admin:accounts_userprofile_changelist")
        user_ids = self._get_filtered_values(
            url, {"past_session_member": "yes"}, field="user_id"
        )
        assert self.past_djangonaut.pk in user_ids
        assert self.past_navigator.pk in user_ids
        assert self.future_djangonaut.pk in user_ids
        assert self.no_session_user.pk not in user_ids

    def test_useravailability_past_djangonaut_yes(self) -> None:
        url = reverse("admin:accounts_useravailability_changelist")
        user_ids = self._get_filtered_values(
            url, {"past_djangonaut": "yes"}, field="user_id"
        )
        assert self.past_djangonaut.pk in user_ids
        assert self.no_session_user.pk not in user_ids

    def test_useravailability_past_session_member_no(self) -> None:
        url = reverse("admin:accounts_useravailability_changelist")
        user_ids = self._get_filtered_values(
            url, {"past_session_member": "no"}, field="user_id"
        )
        assert self.past_djangonaut.pk not in user_ids
        assert self.no_session_user.pk in user_ids

    def test_useravailability_updated_at_filter(self) -> None:
        url = reverse("admin:accounts_useravailability_changelist")
        response = self.client.get(
            url, {"updated_at__gte": "2020-01-01 00:00:00+00:00"}
        )
        assert response.status_code == HTTPStatus.OK


class ExportCsvActionTests(TestCase):
    """Exercise the shared ExportCsvMixin.export_as_csv admin action."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.superuser = CustomUser.objects.create_superuser(
            username="admin", email="admin@example.com", password="test"
        )

    def setUp(self) -> None:
        self.client.force_login(self.superuser)

    def test_export_returns_csv_attachment_with_selected_rows(self) -> None:
        url = reverse("admin:accounts_customuser_changelist")

        response = self.client.post(
            url,
            {"action": "export_as_csv", "_selected_action": [self.superuser.pk]},
        )

        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response["Content-Type"], "text/csv")
        self.assertIn("attachment; filename=", response["Content-Disposition"])

        content = response.content.decode()
        self.assertIn("username", content)
        self.assertIn("admin@example.com", content)
        self.assertNotIn("password", content)

    def test_export_with_empty_queryset_writes_header_only(self) -> None:
        model_admin = CustomUserAdmin(CustomUser, admin.site)
        request = RequestFactory().get("/")

        response = model_admin.export_as_csv(request, CustomUser.objects.none())

        self.assertEqual(response["Content-Type"], "text/csv")
        rows = response.content.decode().strip().splitlines()
        self.assertEqual(len(rows), 1)
        self.assertIn("username", rows[0])


class CompareAvailabilityActionTests(TestCase):
    """Cover both branches of CustomUserAdmin.compare_availability_action."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.superuser = CustomUser.objects.create_superuser(
            username="admin", email="admin@example.com", password="test"
        )
        cls.user_1 = UserFactory.create(username="user_1")
        cls.user_2 = UserFactory.create(username="user_2")

    def setUp(self) -> None:
        self.client.force_login(self.superuser)

    def test_redirects_to_compare_page_with_selected_user_ids(self) -> None:
        url = reverse("admin:accounts_customuser_changelist")

        response = self.client.post(
            url,
            {
                "action": "compare_availability_action",
                "_selected_action": [self.user_1.pk, self.user_2.pk],
            },
        )

        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        expected_prefix = f"{reverse('compare_availability')}?users="
        self.assertTrue(response["Location"].startswith(expected_prefix))
        self.assertIn(str(self.user_1.pk), response["Location"])
        self.assertIn(str(self.user_2.pk), response["Location"])

    def test_empty_selection_messages_user_and_returns_none(self) -> None:
        model_admin = CustomUserAdmin(CustomUser, admin.site)
        model_admin.message_user = MagicMock()
        request = RequestFactory().post("/")

        result = model_admin.compare_availability_action(
            request, CustomUser.objects.none()
        )

        self.assertIsNone(result)
        model_admin.message_user.assert_called_once()


class GroupAdminActionTests(TestCase):
    """Cover CustomGroupAdmin.recreate_session_organizers_group action."""

    @classmethod
    def setUpTestData(cls) -> None:
        cls.superuser = CustomUser.objects.create_superuser(
            username="admin", email="admin@example.com", password="test"
        )
        cls.group = Group.objects.create(name="Session Organizers")

    def setUp(self) -> None:
        self.client.force_login(self.superuser)

    def test_recreate_session_organizers_group_runs_command(self) -> None:
        url = reverse("admin:auth_group_changelist")

        with patch("accounts.admin.call_command") as mock_call_command:
            response = self.client.post(
                url,
                {
                    "action": "recreate_session_organizers_group",
                    "_selected_action": [self.group.pk],
                },
            )

        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        mock_call_command.assert_called_once_with("setup_session_organizers_group")
