from datetime import timedelta
from http import HTTPStatus

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.factories import UserAvailabilityFactory, UserFactory
from accounts.models import CustomUser
from home.factories import SessionFactory, SessionMembershipFactory
from home.models import SessionMembership


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
            role=SessionMembership.DJANGONAUT,
            team=None,
        )

        cls.past_navigator = UserFactory.create(username="past_navigator")
        SessionMembershipFactory.create(
            user=cls.past_navigator,
            session=past_session,
            role=SessionMembership.NAVIGATOR,
            team=None,
        )

        cls.future_djangonaut = UserFactory.create(username="future_djangonaut")
        SessionMembershipFactory.create(
            user=cls.future_djangonaut,
            session=future_session,
            role=SessionMembership.DJANGONAUT,
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
        response = self.client.get(url, {"updated_at__gte": "2020-01-01"})
        assert response.status_code == HTTPStatus.OK
