"""Tests for the testimonial feature."""

from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.factories import UserFactory
from home.factories import (
    SessionFactory,
    SessionMembershipFactory,
    TestimonialFactory,
)
from home.forms import TestimonialForm
from home.models import SessionMembership, Testimonial
from home.tasks.testimonial_notifications import send_testimonial_notification


class TestimonialModelTests(TestCase):
    """Tests for the Testimonial model."""

    def test_str_representation(self):
        """Test the string representation of a testimonial."""
        testimonial = TestimonialFactory.create()
        expected = f"{testimonial.title} - {testimonial.author}"
        self.assertEqual(str(testimonial), expected)

    def test_slug_auto_generated(self):
        """Test that slug is auto-generated from author name, title, and unique code."""
        testimonial = TestimonialFactory.create(title="My Great Experience")
        self.assertIn("my-great-experience", testimonial.slug)
        # Slug should contain author's first name (or 'anon') and a 6-char hex code
        name = (
            testimonial.author.first_name.lower()
            if testimonial.author.first_name
            else "anon"
        )
        self.assertTrue(testimonial.slug.startswith(name))
        # Should end with a 6-character hex code
        self.assertRegex(testimonial.slug, r"-[a-f0-9]{6}$")

    def test_get_absolute_url(self):
        """Test get_absolute_url returns correct URL."""
        testimonial = TestimonialFactory.create()
        url = testimonial.get_absolute_url()
        self.assertIn("/testimonials/", url)
        self.assertIn(f"#{testimonial.slug}", url)

    def test_unique_constraint(self):
        """Test that a user can only have one testimonial per session."""
        user = UserFactory.create()
        session = SessionFactory.create()
        TestimonialFactory.create(author=user, session=session)

        with self.assertRaises(Exception):
            TestimonialFactory.create(author=user, session=session)


class TestimonialQuerySetTests(TestCase):
    """Tests for the TestimonialQuerySet."""

    def setUp(self):
        self.user = UserFactory.create()
        self.other_user = UserFactory.create()
        self.session = SessionFactory.create()

    def test_published(self):
        """Test published() returns only published testimonials."""
        published = TestimonialFactory.create(is_published=True)
        unpublished = TestimonialFactory.create(is_published=False)

        qs = Testimonial.objects.published()
        self.assertIn(published, qs)
        self.assertNotIn(unpublished, qs)

    def test_for_user(self):
        """Test for_user() returns only testimonials by that user."""
        user_testimonial = TestimonialFactory.create(author=self.user)
        other_testimonial = TestimonialFactory.create(author=self.other_user)

        qs = Testimonial.objects.for_user(self.user)
        self.assertIn(user_testimonial, qs)
        self.assertNotIn(other_testimonial, qs)

    def test_for_admin_site_superuser(self):
        """Test for_admin_site() returns all testimonials for superuser."""
        superuser = UserFactory.create(is_superuser=True)
        testimonial1 = TestimonialFactory.create()
        testimonial2 = TestimonialFactory.create()

        qs = Testimonial.objects.for_admin_site(superuser)
        self.assertIn(testimonial1, qs)
        self.assertIn(testimonial2, qs)

    def test_for_admin_site_organizer(self):
        """Test for_admin_site() returns only session testimonials for organizer."""
        organizer = UserFactory.create()
        session = SessionFactory.create()
        SessionMembershipFactory.create(
            user=organizer, session=session, role=SessionMembership.ORGANIZER
        )

        session_testimonial = TestimonialFactory.create(session=session)
        other_testimonial = TestimonialFactory.create()

        qs = Testimonial.objects.for_admin_site(organizer)
        self.assertIn(session_testimonial, qs)
        self.assertNotIn(other_testimonial, qs)


class TestimonialListViewTests(TestCase):
    """Tests for the TestimonialListView."""

    def setUp(self):
        self.client = Client()
        self.url = reverse("testimonial_list")

    def test_list_view_shows_published_only(self):
        """Test that list view only shows published testimonials."""
        published = TestimonialFactory.create(is_published=True)
        unpublished = TestimonialFactory.create(is_published=False)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, published.title)
        self.assertNotContains(response, unpublished.title)

    def test_list_view_empty_state(self):
        """Test that list view shows empty state when no testimonials."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No testimonials yet")


class TestimonialCreateViewTests(TestCase):
    """Tests for the TestimonialCreateView."""

    def setUp(self):
        self.client = Client()
        self.user = UserFactory.create()
        self.session = SessionFactory.create()
        # Create membership so user can create testimonial for this session
        SessionMembershipFactory.create(
            user=self.user,
            session=self.session,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )
        self.url = reverse("testimonial_create")

    def test_create_view_requires_login(self):
        """Test that create view requires authentication."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response.url)

    def test_create_view_shows_form(self):
        """Test that create view shows form for authenticated user."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Share Your Experience")

    def test_create_view_filters_sessions(self):
        """Test that form only shows sessions user has membership in."""
        self.client.force_login(self.user)
        other_session = SessionFactory.create()

        response = self.client.get(self.url)

        form = response.context["form"]
        session_ids = list(form.fields["session"].queryset.values_list("pk", flat=True))
        self.assertIn(self.session.pk, session_ids)
        self.assertNotIn(other_session.pk, session_ids)

    def test_create_view_creates_testimonial(self):
        """Test that create view creates testimonial."""
        self.client.force_login(self.user)
        data = {
            "title": "My Great Experience",
            "text": "This was an amazing program that helped me learn so much about Django!",
            "session": self.session.pk,
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        testimonial = Testimonial.objects.get(title="My Great Experience")
        self.assertEqual(testimonial.author, self.user)
        self.assertEqual(testimonial.session, self.session)
        self.assertFalse(testimonial.is_published)

    def test_create_view_redirects_user_without_memberships(self):
        """Test that users without session memberships are redirected."""
        user_without_membership = UserFactory.create()
        self.client.force_login(user_without_membership)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("testimonial_list"))


class TestimonialUpdateViewTests(TestCase):
    """Tests for the TestimonialUpdateView."""

    def setUp(self):
        self.client = Client()
        self.user = UserFactory.create()
        self.session = SessionFactory.create()
        SessionMembershipFactory.create(
            user=self.user,
            session=self.session,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )
        self.testimonial = TestimonialFactory.create(
            author=self.user,
            session=self.session,
            is_published=True,
        )
        self.url = reverse("testimonial_edit", kwargs={"slug": self.testimonial.slug})

    def test_update_view_requires_login(self):
        """Test that update view requires authentication."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_update_view_requires_author(self):
        """Test that only the author can edit their testimonial."""
        other_user = UserFactory.create()
        self.client.force_login(other_user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_update_view_shows_form(self):
        """Test that update view shows form with existing data."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.testimonial.title)
        self.assertContains(response, "Edit Your Testimonial")

    def test_update_view_unpublishes_on_edit(self):
        """Test that editing a testimonial unpublishes it."""
        self.client.force_login(self.user)
        self.assertTrue(self.testimonial.is_published)

        data = {
            "title": "Updated Title",
            "text": "Updated text content that is long enough to pass validation test.",
            "session": self.session.pk,
        }

        response = self.client.post(self.url, data)

        self.assertEqual(response.status_code, 302)
        self.testimonial.refresh_from_db()
        self.assertEqual(self.testimonial.title, "Updated Title")
        self.assertFalse(self.testimonial.is_published)


class TestimonialDeleteViewTests(TestCase):
    """Tests for the TestimonialDeleteView."""

    def setUp(self):
        self.client = Client()
        self.user = UserFactory.create()
        self.testimonial = TestimonialFactory.create(author=self.user)
        self.url = reverse("testimonial_delete", kwargs={"slug": self.testimonial.slug})

    def test_delete_view_requires_login(self):
        """Test that delete view requires authentication."""
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 302)

    def test_delete_view_requires_author(self):
        """Test that only the author can delete their testimonial."""
        other_user = UserFactory.create()
        self.client.force_login(other_user)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 403)

    def test_delete_view_shows_confirmation(self):
        """Test that delete view shows confirmation page."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Delete Testimonial")
        self.assertContains(response, self.testimonial.title)

    def test_delete_view_deletes_testimonial(self):
        """Test that delete view deletes the testimonial."""
        self.client.force_login(self.user)
        testimonial_pk = self.testimonial.pk

        response = self.client.post(self.url)

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Testimonial.objects.filter(pk=testimonial_pk).exists())


class TestimonialFormTests(TestCase):
    """Tests for the TestimonialForm."""

    def setUp(self):
        self.user = UserFactory.create()
        self.session = SessionFactory.create()
        SessionMembershipFactory.create(
            user=self.user,
            session=self.session,
            role=SessionMembership.DJANGONAUT,
            accepted=True,
        )

    def test_form_filters_sessions_to_user_memberships(self):
        """Test that form only shows sessions user has membership in."""
        other_session = SessionFactory.create()

        form = TestimonialForm(user=self.user)

        session_ids = list(form.fields["session"].queryset.values_list("pk", flat=True))
        self.assertIn(self.session.pk, session_ids)
        self.assertNotIn(other_session.pk, session_ids)

    def test_form_validates_minimum_text_length(self):
        """Test that form requires minimum text length."""
        form = TestimonialForm(
            user=self.user,
            data={
                "title": "My Title",
                "text": "Too short",
                "session": self.session.pk,
            },
        )

        self.assertFalse(form.is_valid())
        self.assertIn("text", form.errors)


class TestimonialAdminTests(TestCase):
    """Tests for the TestimonialAdmin."""

    def setUp(self):
        self.superuser = UserFactory.create(is_superuser=True, is_staff=True)
        self.client = Client()
        self.client.force_login(self.superuser)

    def test_admin_list_view(self):
        """Test that admin list view works."""
        testimonial = TestimonialFactory.create()
        url = reverse("admin:home_testimonial_changelist")

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, testimonial.title)

    def test_admin_publish_action(self):
        """Test the publish action works."""
        testimonial = TestimonialFactory.create(is_published=False)
        url = reverse("admin:home_testimonial_changelist")

        response = self.client.post(
            url,
            {
                "action": "publish_testimonials",
                "_selected_action": [testimonial.pk],
            },
        )

        self.assertEqual(response.status_code, 302)
        testimonial.refresh_from_db()
        self.assertTrue(testimonial.is_published)

    def test_admin_unpublish_action(self):
        """Test the unpublish action works."""
        testimonial = TestimonialFactory.create(is_published=True)
        url = reverse("admin:home_testimonial_changelist")

        response = self.client.post(
            url,
            {
                "action": "unpublish_testimonials",
                "_selected_action": [testimonial.pk],
            },
        )

        self.assertEqual(response.status_code, 302)
        testimonial.refresh_from_db()
        self.assertFalse(testimonial.is_published)


class ProfileTestimonialsSectionTests(TestCase):
    """Tests for the testimonials section on the profile page."""

    def setUp(self):
        self.client = Client()
        self.user = UserFactory.create()
        session = SessionFactory.create()
        SessionMembershipFactory.create(
            user=self.user, session=session, role=SessionMembership.DJANGONAUT
        )
        self.url = reverse("profile")

    def test_profile_shows_testimonials_section(self):
        """Test that profile page shows testimonials section."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Testimonials")

    def test_profile_shows_user_testimonials(self):
        """Test that profile page shows user's testimonials."""
        self.client.force_login(self.user)
        testimonial = TestimonialFactory.create(author=self.user)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, testimonial.title)

    def test_profile_shows_published_status(self):
        """Test that profile page shows correct status for testimonials."""
        self.client.force_login(self.user)
        TestimonialFactory.create(author=self.user, is_published=True)
        TestimonialFactory.create(
            author=self.user, is_published=False, session=SessionFactory.create()
        )
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Published")
        self.assertContains(response, "Pending Review")

    def test_profile_shows_add_new_link(self):
        """Test that profile page shows link to create new testimonial."""
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("testimonial_create"))

    def test_profile_hides_add_new_link_when_not_a_session_member(self):
        """
        Test that profile page hides link to create new testimonial
        when they aren't a session member.
        """
        SessionMembership.objects.filter(user=self.user).delete()
        self.client.force_login(self.user)
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, reverse("testimonial_create"))


class SendTestimonialNotificationTaskTests(TestCase):
    """Tests for the send_testimonial_notification task."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = UserFactory.create(
            is_superuser=True, is_active=True, email="admin@example.com"
        )
        cls.session = SessionFactory.create(title="Test Session 2024")
        cls.author = UserFactory.create(
            email="author@example.com", first_name="TestAuthor"
        )
        cls.testimonial = TestimonialFactory.create(
            title="Great Experience",
            text="This was an amazing program!",
            author=cls.author,
            session=cls.session,
        )

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.testimonial_notifications.email.send")
    def test_sends_notification_for_new_testimonial(self, mock_send):
        """Test that task sends notification email for a new testimonial."""
        send_testimonial_notification.call(
            testimonial_id=self.testimonial.pk,
            is_new=True,
        )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["email_template"], "testimonial_notification")
        self.assertEqual(call_kwargs["recipient_list"], ["admin@example.com"])
        self.assertEqual(call_kwargs["context"]["testimonial"], self.testimonial)
        self.assertEqual(call_kwargs["context"]["author"], self.author)
        self.assertEqual(call_kwargs["context"]["session"], self.session)
        self.assertTrue(call_kwargs["context"]["is_new"])
        self.assertIn("admin_url", call_kwargs["context"])
        self.assertIn("cta_link", call_kwargs["context"])

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.testimonial_notifications.email.send")
    def test_sends_notification_for_updated_testimonial(self, mock_send):
        """Test that task sends notification email for an updated testimonial."""
        old_values = {
            "title": "Old Title",
            "text": "Old text content",
            "session_id": self.session.pk,
        }

        send_testimonial_notification.call(
            testimonial_id=self.testimonial.pk,
            is_new=False,
            old_values=old_values,
        )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        self.assertEqual(call_kwargs["email_template"], "testimonial_notification")
        self.assertFalse(call_kwargs["context"]["is_new"])
        # Should include changes for title and text
        changes = call_kwargs["context"]["changes"]
        self.assertEqual(len(changes), 2)
        title_change = next(c for c in changes if c["field"] == "Title")
        self.assertEqual(title_change["old"], "Old Title")
        self.assertEqual(title_change["new"], "Great Experience")
        text_change = next(c for c in changes if c["field"] == "Text")
        self.assertEqual(text_change["old"], "Old text content")
        self.assertEqual(text_change["new"], "This was an amazing program!")

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.testimonial_notifications.email.send")
    def test_sends_notification_with_session_change(self, mock_send):
        """Test that task includes session change in notification."""
        old_session = SessionFactory.create(title="Old Session 2023")
        old_values = {
            "title": self.testimonial.title,
            "text": self.testimonial.text,
            "session_id": old_session.pk,
        }

        send_testimonial_notification.call(
            testimonial_id=self.testimonial.pk,
            is_new=False,
            old_values=old_values,
        )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        changes = call_kwargs["context"]["changes"]
        self.assertEqual(len(changes), 1)
        session_change = changes[0]
        self.assertEqual(session_change["field"], "Session")
        self.assertEqual(session_change["old"], "Old Session 2023")
        self.assertEqual(session_change["new"], "Test Session 2024")

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.testimonial_notifications.email.send")
    def test_does_not_send_email_when_no_superusers(self, mock_send):
        """Test that task does not send email if no superusers exist."""
        # Deactivate the superuser
        self.superuser.is_active = False
        self.superuser.save()

        try:
            send_testimonial_notification.call(
                testimonial_id=self.testimonial.pk,
                is_new=True,
            )
            mock_send.assert_not_called()
        finally:
            # Restore superuser for other tests
            self.superuser.is_active = True
            self.superuser.save()

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.testimonial_notifications.email.send")
    def test_sends_to_multiple_superusers(self, mock_send):
        """Test that task sends email to all superusers."""
        second_superuser = UserFactory.create(
            is_superuser=True, is_active=True, email="admin2@example.com"
        )

        try:
            send_testimonial_notification.call(
                testimonial_id=self.testimonial.pk,
                is_new=True,
            )

            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args[1]
            self.assertIn("admin@example.com", call_kwargs["recipient_list"])
            self.assertIn("admin2@example.com", call_kwargs["recipient_list"])
        finally:
            second_superuser.delete()

    @override_settings(
        ENVIRONMENT="production",
        BASE_URL="https://djangonaut.space",
    )
    @patch("home.tasks.testimonial_notifications.email.send")
    def test_handles_deleted_old_session(self, mock_send):
        """Test that task handles case where old session no longer exists."""
        old_values = {
            "title": self.testimonial.title,
            "text": self.testimonial.text,
            "session_id": 99999,  # Non-existent session ID
        }

        send_testimonial_notification.call(
            testimonial_id=self.testimonial.pk,
            is_new=False,
            old_values=old_values,
        )

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args[1]
        changes = call_kwargs["context"]["changes"]
        session_change = changes[0]
        self.assertEqual(session_change["old"], "Unknown")
