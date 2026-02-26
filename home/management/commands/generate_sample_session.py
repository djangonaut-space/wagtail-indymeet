"""
Generate a sample session with a small set of participants for development testing.

This command creates:
- 1 session with basic configuration
- 1 organizer membership for the first superuser
- 2 djangonaut users with memberships
- 1 navigator user with membership
- 1 captain user with membership
"""

from datetime import timedelta

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from accounts.models import CustomUser
from home.factories import SessionFactory, TeamFactory
from home.models import Project, Session, SessionMembership, Team


class Command(BaseCommand):
    help = "Generate a sample session with 5 participants for development testing"

    def handle(self, *args, **options):
        with transaction.atomic():
            today = timezone.now().date()
            date_str = today.strftime("%Y%m%d")
            slug = f"sample-session-{date_str}"
            deleted, _ = Session.objects.filter(slug=slug).delete()
            if deleted:
                self.stdout.write(f"Deleted existing session with slug={slug}")
            session = SessionFactory.create(
                title=f"Sample Session {date_str}",
                slug=slug,
                start_date=today,
                end_date=today + timedelta(weeks=12),
                application_start_date=today - timedelta(weeks=4),
                application_end_date=today - timedelta(weeks=1),
                invitation_date=today - timedelta(days=3),
            )
            self.stdout.write(f"Created session: {session.title} (slug={session.slug})")

            project, _ = Project.objects.get_or_create(
                name="Django Sample Project",
                defaults={"url": "https://github.com/django/django"},
            )
            session.available_projects.add(project)

            team = TeamFactory.create(session=session, name="Team Alpha", project=project)
            self.stdout.write(f"Created team: {team.name}")

            organizer = self._get_superuser()
            self._add_organizer_membership(organizer, session)
            self.stdout.write(f"Added organizer: {organizer.username}")

            for i in range(1, 3):
                user, _ = CustomUser.objects.get_or_create(
                    username=f"sample_djangonaut_{date_str}_{i}",
                    defaults={
                        "email": f"djangonaut{i}_{date_str}@sample.example.com",
                        "first_name": f"Djangonaut{i}",
                        "last_name": "Sample",
                    },
                )
                user.set_password("testpass123")
                user.save(update_fields=["password"])
                SessionMembership.objects.get_or_create(
                    user=user,
                    session=session,
                    defaults={"team": team, "role": SessionMembership.DJANGONAUT, "accepted": True},
                )
                self.stdout.write(f"Added djangonaut: {user.username}")

            navigator, _ = CustomUser.objects.get_or_create(
                username=f"sample_navigator_{date_str}",
                defaults={
                    "email": f"navigator_{date_str}@sample.example.com",
                    "first_name": "Navigator",
                    "last_name": "Sample",
                },
            )
            navigator.set_password("testpass123")
            navigator.save(update_fields=["password"])
            SessionMembership.objects.get_or_create(
                user=navigator,
                session=session,
                defaults={"team": team, "role": SessionMembership.NAVIGATOR, "accepted": True},
            )
            self.stdout.write(f"Added navigator: {navigator.username}")

            captain, _ = CustomUser.objects.get_or_create(
                username=f"sample_captain_{date_str}",
                defaults={
                    "email": f"captain_{date_str}@sample.example.com",
                    "first_name": "Captain",
                    "last_name": "Sample",
                },
            )
            captain.set_password("testpass123")
            captain.save(update_fields=["password"])
            SessionMembership.objects.get_or_create(
                user=captain,
                session=session,
                defaults={"team": team, "role": SessionMembership.CAPTAIN, "accepted": True},
            )
            self.stdout.write(f"Added captain: {captain.username}")

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSuccessfully created sample session '{session.title}':"
                )
            )
            self.stdout.write(f"  Organizer:    {organizer.username}")
            self.stdout.write(f"  Djangonauts:  sample_djangonaut_{date_str}_1, sample_djangonaut_{date_str}_2")
            self.stdout.write(f"  Navigator:    {navigator.username}")
            self.stdout.write(f"  Captain:      {captain.username}")
            self.stdout.write(f"  Team:         {team.name}")
            self.stdout.write(f"  Project:      {project.name}")

    def _get_superuser(self) -> CustomUser:
        """Return the first available superuser."""
        user = CustomUser.objects.filter(is_superuser=True).first()
        if user is None:
            raise SystemExit("No superuser found. Run manage.py createsuperuser first.")
        return user

    def _add_organizer_membership(
        self, organizer: CustomUser, session
    ) -> SessionMembership:
        """Create organizer membership and grant required permissions."""
        membership = SessionMembership.objects.create(
            user=organizer,
            session=session,
            team=None,
            role=SessionMembership.ORGANIZER,
            accepted=True,
        )

        content_type = ContentType.objects.get_for_model(Team)
        permissions = Permission.objects.filter(
            codename__in=["compare_org_availability", "form_team"],
            content_type=content_type,
        )
        organizer.user_permissions.add(*permissions)

        return membership
