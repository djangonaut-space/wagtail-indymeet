"""Tests for Event audience behaviour."""

from django.core.exceptions import ValidationError
from django.test import TestCase

from accounts.factories import UserFactory
from home import constants
from home.factories import EventFactory, SessionFactory, SessionMembershipFactory
from home.models import Event


class EventAudienceInviteTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.session = SessionFactory.create()
        cls.other_session = SessionFactory.create()
        cls.member = UserFactory.create(email="member@example.com")
        cls.alumnus = UserFactory.create(email="alumnus@example.com")
        cls.unaccepted = UserFactory.create(email="unaccepted@example.com")
        SessionMembershipFactory.create(user=cls.member, session=cls.session)
        SessionMembershipFactory.create(user=cls.alumnus, session=cls.other_session)
        SessionMembershipFactory.create(
            user=cls.unaccepted,
            session=cls.session,
            role=constants.DJANGONAUT,
            accepted=False,
        )

    def test_public_event_invites_only_extra_emails(self):
        event = EventFactory.create(
            audience=Event.Audience.PUBLIC,
            session=self.session,
            extra_emails=["guest@example.com"],
        )
        self.assertEqual(event.get_calendar_invite_recipients(), ["guest@example.com"])

    def test_session_event_invites_accepted_session_members(self):
        event = EventFactory.create(
            audience=Event.Audience.SESSION, session=self.session
        )
        self.assertEqual(event.get_calendar_invite_recipients(), ["member@example.com"])

    def test_session_event_without_session_invites_nobody(self):
        event = EventFactory.create(audience=Event.Audience.SESSION, session=None)
        self.assertEqual(event.get_calendar_invite_recipients(), [])

    def test_community_event_invites_every_accepted_member(self):
        """A community event linked to a session still invites other sessions' members."""
        event = EventFactory.create(
            audience=Event.Audience.COMMUNITY, session=self.session
        )
        self.assertEqual(
            event.get_calendar_invite_recipients(),
            ["alumnus@example.com", "member@example.com"],
        )


class EventCleanTests(TestCase):
    def test_session_audience_requires_session(self):
        event = EventFactory.build(audience=Event.Audience.SESSION, session=None)
        with self.assertRaises(ValidationError) as ctx:
            event.clean()
        self.assertIn("session", ctx.exception.message_dict)

    def test_session_audience_with_session_is_valid(self):
        event = EventFactory.build(
            audience=Event.Audience.SESSION, session=SessionFactory.create()
        )
        event.clean()

    def test_community_audience_without_session_is_valid(self):
        event = EventFactory.build(audience=Event.Audience.COMMUNITY, session=None)
        event.clean()
