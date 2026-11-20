from datetime import datetime
from datetime import timezone as dt_timezone

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone
import time_machine

from accounts.factories import UserFactory
from home import constants
from home.factories import EventFactory, SessionFactory, SessionMembershipFactory
from home.models import Event, SessionMembership
from tests.timezones import CENTRAL_EUROPEAN_TIMEZONE


@time_machine.travel("2012-01-14", tick=False)
class EventViewTests(TestCase):
    def setUp(self):
        self.client = Client()

    @staticmethod
    def create_upcoming_event(**kwargs):
        return EventFactory.create(
            start_time=datetime(2023, 2, 1, 10, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2023, 2, 1, 11, 0, tzinfo=dt_timezone.utc),
            **kwargs,
        )

    @staticmethod
    def create_past_event(**kwargs):
        return EventFactory.create(
            start_time=datetime(2010, 2, 1, 10, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2010, 2, 1, 11, 0, tzinfo=dt_timezone.utc),
            **kwargs,
        )

    def test_list_no_events(self):
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/event_list.html")
        self.assertContains(response, "No upcoming events.")
        self.assertContains(response, "No past events.")

    def test_list_upcoming_events_no_past(self):
        upcoming_event = self.create_upcoming_event()
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/event_list.html")
        self.assertNotContains(response, "No upcoming events.")
        self.assertContains(response, "No past events.")
        self.assertContains(response, upcoming_event.title)
        self.assertContains(response, upcoming_event.get_absolute_url())

    def test_list_upcoming_events_and_past(self):
        upcoming_event = self.create_upcoming_event()
        past_event = self.create_past_event()
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/event_list.html")
        self.assertNotContains(response, "No upcoming events.")
        self.assertNotContains(response, "No past events.")
        self.assertContains(response, upcoming_event.title)
        self.assertContains(response, upcoming_event.get_absolute_url())
        self.assertContains(response, past_event.title)
        self.assertContains(response, past_event.get_absolute_url())

    def test_event_detail(self):
        upcoming_event = self.create_upcoming_event()
        timezone.activate(CENTRAL_EUROPEAN_TIMEZONE)  # UTC + 1
        response = self.client.get(upcoming_event.get_absolute_url())
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed("home/event_detail.html")
        self.assertContains(response, "Feb 01, 2023 11:00 CET")
        timezone.deactivate()


class PrivateEventAccessTests(TestCase):
    """Test that private events are only visible to session members."""

    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create()
        cls.member_user = UserFactory.create()
        cls.non_member_user = UserFactory.create()

        SessionMembershipFactory.create(
            user=cls.member_user,
            session=cls.session,
            role=constants.DJANGONAUT,
            accepted=True,
        )

        cls.private_event = EventFactory.create(
            start_time=datetime(2023, 2, 1, 10, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2023, 2, 1, 11, 0, tzinfo=dt_timezone.utc),
            audience=Event.Audience.SESSION,
            session=cls.session,
        )

    def test_list_hides_private_event_from_anonymous(self):
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.private_event.title)

    def test_list_shows_private_event_to_session_member(self):
        self.client.force_login(self.member_user)
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.private_event.title)

    def test_list_hides_private_event_from_non_member(self):
        self.client.force_login(self.non_member_user)
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.private_event.title)

    def test_detail_redirects_anonymous_to_login(self):
        url = self.private_event.get_absolute_url()
        response = self.client.get(url)
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={url}",
            fetch_redirect_response=False,
        )

    def test_detail_returns_404_for_non_member_on_private_event(self):
        self.client.force_login(self.non_member_user)
        response = self.client.get(self.private_event.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_detail_is_accessible_to_session_member(self):
        self.client.force_login(self.member_user)
        response = self.client.get(self.private_event.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_public_event_visible_to_anonymous(self):
        public_event = EventFactory.create(
            start_time=datetime(2023, 3, 1, 10, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2023, 3, 1, 11, 0, tzinfo=dt_timezone.utc),
        )
        response = self.client.get(reverse("event_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, public_event.title)


class CommunityEventDetailTests(TestCase):
    """Community events are emailed to every accepted member of any session,
    so they can all open them."""

    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create()
        cls.event = EventFactory.create(
            start_time=datetime(2026, 12, 1, 0, 30, tzinfo=dt_timezone.utc),
            end_time=datetime(2026, 12, 1, 1, 30, tzinfo=dt_timezone.utc),
            audience=Event.Audience.COMMUNITY,
            session=cls.session,
        )
        SessionMembershipFactory.create(
            session=cls.session, role=constants.DJANGONAUT, accepted=True
        )
        cls.other_session_member = UserFactory.create()
        SessionMembershipFactory.create(
            user=cls.other_session_member, role=constants.DJANGONAUT, accepted=True
        )

    def test_anonymous_redirects_to_login(self):
        url = self.event.get_absolute_url()
        response = self.client.get(url)
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={url}",
            fetch_redirect_response=False,
        )

    def test_user_without_membership(self):
        self.client.force_login(UserFactory.create())
        response = self.client.get(self.event.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_unaccepted_member(self):
        user = UserFactory.create()
        SessionMembershipFactory.create(
            user=user, role=constants.DJANGONAUT, accepted=False
        )
        self.client.force_login(user)
        response = self.client.get(self.event.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_member_of_other_session(self):
        self.client.force_login(self.other_session_member)
        response = self.client.get(self.event.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_unpublished(self):
        """is_published only gates public events."""
        event = EventFactory.create(
            start_time=datetime(2026, 12, 2, 10, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2026, 12, 2, 11, 0, tzinfo=dt_timezone.utc),
            audience=Event.Audience.COMMUNITY,
            is_published=False,
        )
        self.client.force_login(self.other_session_member)
        response = self.client.get(event.get_absolute_url())
        self.assertEqual(response.status_code, 200)

    def test_unpublished_anonymous_redirects_to_login(self):
        event = EventFactory.create(
            start_time=datetime(2026, 12, 2, 10, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2026, 12, 2, 11, 0, tzinfo=dt_timezone.utc),
            audience=Event.Audience.COMMUNITY,
            is_published=False,
        )
        url = event.get_absolute_url()
        response = self.client.get(url)
        self.assertRedirects(
            response,
            f"{reverse('login')}?next={url}",
            fetch_redirect_response=False,
        )


class UnpublishedPublicEventDetailTests(TestCase):
    """Unpublished public events are drafts: only staff can open them."""

    @classmethod
    def setUpTestData(cls):
        cls.event = EventFactory.create(
            start_time=datetime(2023, 4, 1, 10, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2023, 4, 1, 11, 0, tzinfo=dt_timezone.utc),
            is_published=False,
        )

    def test_detail_returns_404_for_anonymous(self):
        response = self.client.get(self.event.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_detail_returns_404_for_non_staff(self):
        self.client.force_login(UserFactory.create())
        response = self.client.get(self.event.get_absolute_url())
        self.assertEqual(response.status_code, 404)

    def test_detail_is_previewable_by_staff(self):
        self.client.force_login(UserFactory.create(is_staff=True))
        response = self.client.get(self.event.get_absolute_url())
        self.assertEqual(response.status_code, 200)
