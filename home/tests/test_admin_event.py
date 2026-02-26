"""Tests for EventAdmin copy_event and send_calendar_invites actions."""

from datetime import datetime, timezone as dt_timezone
from unittest.mock import patch

from django.contrib.admin.sites import AdminSite
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponseRedirect
from django.test import RequestFactory, TestCase
from django.urls import reverse

from accounts.factories import UserFactory
from home.admin import EventAdmin
from home.factories import EventFactory, SessionFactory, SessionMembershipFactory
from home.models import Event


class EventAdminCopyActionTests(TestCase):
    """Tests for the copy_event admin action."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = EventAdmin(Event, AdminSite())
        self.superuser = UserFactory.create(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
        )
        self.event = EventFactory.create(
            title="Original Event",
            slug="original-event",
            start_time=datetime(2025, 6, 1, 18, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2025, 6, 1, 20, 0, tzinfo=dt_timezone.utc),
            location="https://zoom.example.com",
            status=Event.SCHEDULED,
        )

    def _get_request(self):
        """Build a POST request with session and messages support."""
        request = self.factory.post("/admin/home/event/")
        request.user = self.superuser
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        messages = FallbackStorage(request)
        request._messages = messages
        return request

    def test_copy_event_redirects_to_add_form_with_copy_from(self):
        """Action redirects to the add form with copy_from pointing to the original."""
        request = self._get_request()
        queryset = Event.objects.filter(pk=self.event.pk)

        response = self.admin.copy_event(request, queryset)

        self.assertIsInstance(response, HttpResponseRedirect)
        expected_url = reverse("admin:home_event_add")
        self.assertIn(expected_url, response.url)
        self.assertIn(f"copy_from={self.event.pk}", response.url)

    def test_copy_event_error_when_multiple_selected(self):
        """Action shows an error and returns None when more than one event is selected."""
        EventFactory.create(
            title="Second Event",
            slug="second-event",
            start_time=datetime(2025, 7, 1, 18, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2025, 7, 1, 20, 0, tzinfo=dt_timezone.utc),
        )
        request = self._get_request()
        queryset = Event.objects.all()

        response = self.admin.copy_event(request, queryset)

        self.assertIsNone(response)
        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertIn("exactly one", str(stored[0]))

    def test_copy_event_does_not_create_new_event(self):
        """Action must not persist any new event record — only a redirect."""
        request = self._get_request()
        queryset = Event.objects.filter(pk=self.event.pk)
        count_before = Event.objects.count()

        self.admin.copy_event(request, queryset)

        self.assertEqual(Event.objects.count(), count_before)


class EventAdminGetChangeformInitialDataTests(TestCase):
    """Tests for get_changeform_initial_data pre-population via copy_from."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = EventAdmin(Event, AdminSite())
        self.superuser = UserFactory.create(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
        )
        self.speaker = UserFactory.create(email="speaker@example.com")
        self.organizer = UserFactory.create(email="organizer@example.com")
        self.event = EventFactory.create(
            title="Source Event",
            slug="source-event",
            start_time=datetime(2025, 6, 1, 18, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2025, 6, 1, 20, 0, tzinfo=dt_timezone.utc),
            location="https://zoom.example.com",
            description="A great event.",
            status=Event.SCHEDULED,
            video_link="https://youtube.example.com/watch?v=abc",
            is_public=True,
            capacity=50,
            extra_emails=["sessions@djangonaut.space"],
        )
        self.event.speakers.add(self.speaker)
        self.event.organizers.add(self.organizer)

    def _get_add_request(self, copy_from=None):
        params = f"?copy_from={copy_from}" if copy_from else ""
        request = self.factory.get(f"/admin/home/event/add/{params}")
        request.user = self.superuser
        return request

    def test_pre_populates_scalar_fields_from_source(self):
        """Scalar fields are pre-populated from the source event."""
        request = self._get_add_request(copy_from=self.event.pk)
        initial = self.admin.get_changeform_initial_data(request)

        self.assertEqual(initial["title"], "Source Event")
        self.assertEqual(initial["slug"], "source-event")
        self.assertEqual(initial["location"], "https://zoom.example.com")
        self.assertEqual(initial["description"], "A great event.")
        self.assertEqual(
            initial["video_link"], "https://youtube.example.com/watch?v=abc"
        )
        self.assertTrue(initial["is_public"])
        self.assertEqual(initial["capacity"], 50)
        self.assertEqual(initial["extra_emails"], ["sessions@djangonaut.space"])

    def test_status_reset_to_pending(self):
        """The copied event's status is reset to Pending regardless of the source."""
        request = self._get_add_request(copy_from=self.event.pk)
        initial = self.admin.get_changeform_initial_data(request)

        self.assertEqual(initial["status"], Event.PENDING)

    def test_pre_populates_m2m_speakers_and_organizers(self):
        """Speaker and organizer querysets are included in initial data."""
        request = self._get_add_request(copy_from=self.event.pk)
        initial = self.admin.get_changeform_initial_data(request)

        speaker_ids = list(initial["speakers"].values_list("pk", flat=True))
        self.assertIn(self.speaker.pk, speaker_ids)

        organizer_ids = list(initial["organizers"].values_list("pk", flat=True))
        self.assertIn(self.organizer.pk, organizer_ids)

    def test_no_copy_from_returns_normal_initial(self):
        """Without copy_from the method behaves like the default implementation."""
        request = self._get_add_request()
        initial = self.admin.get_changeform_initial_data(request)

        self.assertNotIn("title", initial)
        self.assertNotIn("speakers", initial)

    def test_invalid_copy_from_returns_normal_initial(self):
        """A non-existent copy_from pk is silently ignored."""
        request = self._get_add_request(copy_from=999_999)
        initial = self.admin.get_changeform_initial_data(request)

        self.assertNotIn("title", initial)


class EventAdminSendCalendarInvitesTests(TestCase):
    """Tests for the send_calendar_invites admin action."""

    def setUp(self):
        self.factory = RequestFactory()
        self.admin = EventAdmin(Event, AdminSite())
        self.superuser = UserFactory.create(
            email="admin@example.com",
            is_staff=True,
            is_superuser=True,
        )

    def _get_request(self):
        request = self.factory.post("/admin/home/event/")
        request.user = self.superuser
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()
        request._messages = FallbackStorage(request)
        return request

    def _make_event(self, **kwargs):
        return EventFactory.create(
            start_time=datetime(2025, 9, 1, 18, 0, tzinfo=dt_timezone.utc),
            end_time=datetime(2025, 9, 1, 20, 0, tzinfo=dt_timezone.utc),
            **kwargs,
        )

    @patch("home.admin.tasks.send_event_calendar_invite")
    def test_session_event_sends_to_session_members(self, mock_task):
        """A session event queues invites for all session members."""
        session = SessionFactory.create()
        member1 = UserFactory.create(email="member1@example.com")
        member2 = UserFactory.create(email="member2@example.com")
        SessionMembershipFactory.create(session=session, user=member1)
        SessionMembershipFactory.create(session=session, user=member2)
        event = self._make_event(session=session, is_public=True)

        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )

        mock_task.enqueue.assert_called_once()
        _, kwargs = mock_task.enqueue.call_args
        self.assertEqual(kwargs["event_id"], event.pk)
        self.assertIn("member1@example.com", kwargs["recipients"])
        self.assertIn("member2@example.com", kwargs["recipients"])

    @patch("home.admin.tasks.send_event_calendar_invite")
    def test_public_event_no_session_sends_to_opted_in_users(self, mock_task):
        """A public event with no session sends to users who opted in for event updates."""
        opted_in = UserFactory.create(email="opted@example.com")
        opted_in.profile.receiving_event_updates = True
        opted_in.profile.save()

        UserFactory.create(email="nope@example.com")
        # not_opted.profile.receiving_event_updates remains False

        event = self._make_event(is_public=True, session=None)

        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )

        mock_task.enqueue.assert_called_once()
        _, kwargs = mock_task.enqueue.call_args
        self.assertIn("opted@example.com", kwargs["recipients"])
        self.assertNotIn("nope@example.com", kwargs["recipients"])

    @patch("home.admin.tasks.send_event_calendar_invite")
    def test_private_event_no_session_sends_empty_recipients(self, mock_task):
        """A private event with no session passes an empty recipient list.

        The task will still send to extra_emails (e.g. sessions@djangonaut.space).
        """
        event = self._make_event(is_public=False, session=None)

        self.admin.send_calendar_invites(
            self._get_request(), Event.objects.filter(pk=event.pk)
        )

        mock_task.enqueue.assert_called_once()
        _, kwargs = mock_task.enqueue.call_args
        self.assertEqual(kwargs["recipients"], [])

    @patch("home.admin.tasks.send_event_calendar_invite")
    def test_multiple_events_queues_one_task_each(self, mock_task):
        """Selecting multiple events queues one task per event."""
        event1 = self._make_event(slug="ev-1", is_public=False)
        event2 = self._make_event(slug="ev-2", is_public=False)

        self.admin.send_calendar_invites(
            self._get_request(),
            Event.objects.filter(pk__in=[event1.pk, event2.pk]),
        )

        self.assertEqual(mock_task.enqueue.call_count, 2)

    @patch("home.admin.tasks.send_event_calendar_invite")
    def test_success_message_shows_queued_count(self, mock_task):
        """A success message is shown with the number of events processed."""
        event = self._make_event(is_public=False)
        request = self._get_request()

        self.admin.send_calendar_invites(request, Event.objects.filter(pk=event.pk))

        stored = list(request._messages)
        self.assertEqual(len(stored), 1)
        self.assertIn("1", str(stored[0]))
