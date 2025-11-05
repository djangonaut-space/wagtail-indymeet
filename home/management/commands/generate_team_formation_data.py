"""
Generate sample data for team formation testing.

This command creates:
- 50 applicant users with survey responses, scores, and availability
- 3 captain users
- 4 navigator users
- Realistic availability schedules with overlaps
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from faker import Faker

from accounts.models import CustomUser, UserAvailability
from home.models import Session, Survey, UserSurveyResponse


class Command(BaseCommand):
    help = "Generate sample data for team formation testing (session PK=4)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--session-id",
            type=int,
            help="Session ID to generate data for",
        )

    def handle(self, *args, **options):
        session_id = options["session_id"]
        fake = Faker()
        Faker.seed(42)  # Consistent data for testing

        try:
            session = Session.objects.get(pk=session_id)
        except Session.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"Session with ID {session_id} does not exist")
            )
            return

        if not session.application_survey:
            self.stdout.write(
                self.style.ERROR(
                    f"Session {session_id} does not have an application survey"
                )
            )
            return

        survey = session.application_survey

        with transaction.atomic():
            self.stdout.write("Creating 50 djangonaut users...")
            djangonauts = self._create_djangonauts(fake, session, survey, 50)

            self.stdout.write("Creating 3 captain users...")
            captains = self._create_captains(fake, session, survey, 3)

            self.stdout.write("Creating 4 navigator users...")
            navigators = self._create_navigators(fake, session, survey, 4)

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSuccessfully generated data for session {session_id}:"
                )
            )
            self.stdout.write(f"  - {len(djangonauts)} djangonauts with responses")
            self.stdout.write(f"  - {len(captains)} captains")
            self.stdout.write(f"  - {len(navigators)} navigators")
            self.stdout.write("\nAll users have availability schedules with overlaps.")

    def _create_djangonauts(self, fake, session, survey, count):
        """Create djangonaut users (applicants) with survey responses and availability."""
        from home.models import SessionMembership

        djangonauts = []

        for i in range(count):
            # Create user
            username = f"djangonaut_{i+1}_{fake.user_name()[:10]}"
            email = f"djangonaut{i+1}@example.com"

            user = CustomUser.objects.create_user(
                username=username,
                email=email,
                password="testpass123",
                first_name=fake.first_name(),
                last_name=fake.last_name(),
            )

            # Create survey response with score and selection rank
            # Random scores between 5-15
            # Selection ranks distributed randomly between 1-4
            score = fake.random_int(min=5, max=15)
            selection_rank = fake.random_int(min=1, max=4)

            UserSurveyResponse.objects.create(
                user=user, survey=survey, score=score, selection_rank=selection_rank
            )

            # Create SessionMembership with DJANGONAUT role
            SessionMembership.objects.create(
                user=user, session=session, role=SessionMembership.DJANGONAUT
            )

            # Create availability schedule
            # Different patterns to create interesting overlaps
            availability = self._create_availability_pattern(i, fake)
            UserAvailability.objects.create(user=user, slots=availability)

            djangonauts.append(user)

        return djangonauts

    def _create_captains(self, fake, session, survey, count):
        """Create captain users with good availability and session memberships."""
        from home.models import SessionMembership

        captains = []

        for i in range(count):
            username = f"captain_{i+1}_{fake.user_name()[:10]}"
            email = f"captain{i+1}@example.com"

            user = CustomUser.objects.create_user(
                username=username,
                email=email,
                password="testpass123",
                first_name=fake.first_name(),
                last_name=fake.last_name(),
            )

            # Captains also have survey responses (but typically not ranked)
            UserSurveyResponse.objects.create(
                user=user, survey=survey, score=fake.random_int(min=12, max=15)
            )

            # Create SessionMembership
            SessionMembership.objects.create(
                user=user, session=session, role=SessionMembership.CAPTAIN
            )

            # Captains have flexible availability (many time slots)
            # Monday-Friday, 9am-5pm UTC (more availability than applicants)
            availability = []
            for day in range(1, 6):  # Monday to Friday
                for hour in range(9, 17):  # 9am to 5pm
                    availability.extend([day * 24 + hour, day * 24 + hour + 0.5])

            UserAvailability.objects.create(user=user, slots=availability)

            captains.append(user)

        return captains

    def _create_navigators(self, fake, session, survey, count):
        """Create navigator users with good availability and session memberships."""
        from home.models import SessionMembership

        navigators = []

        for i in range(count):
            username = f"navigator_{i+1}_{fake.user_name()[:10]}"
            email = f"navigator{i+1}@example.com"

            user = CustomUser.objects.create_user(
                username=username,
                email=email,
                password="testpass123",
                first_name=fake.first_name(),
                last_name=fake.last_name(),
            )

            # Navigators also have survey responses
            UserSurveyResponse.objects.create(
                user=user, survey=survey, score=fake.random_int(min=13, max=15)
            )

            # Create SessionMembership
            SessionMembership.objects.create(
                user=user, session=session, role=SessionMembership.NAVIGATOR
            )

            # Navigators need consistent availability for team meetings
            # Tuesday-Thursday, 10am-3pm UTC (good overlap window)
            availability = []
            for day in range(2, 5):  # Tuesday to Thursday
                for hour in range(10, 15):  # 10am to 3pm
                    availability.extend([day * 24 + hour, day * 24 + hour + 0.5])

            UserAvailability.objects.create(user=user, slots=availability)

            navigators.append(user)

        return navigators

    def _create_availability_pattern(self, index, fake):
        """
        Create realistic availability patterns with variety.

        Patterns ensure some users will have good overlap while others won't.
        """
        availability = []

        # Pattern groups to create interesting team formation scenarios
        pattern_type = index % 5

        if pattern_type == 0:
            # Morning people: Mon-Fri 8am-12pm UTC
            for day in range(1, 6):
                for hour in range(8, 12):
                    availability.extend([day * 24 + hour, day * 24 + hour + 0.5])

        elif pattern_type == 1:
            # Afternoon people: Mon-Fri 1pm-5pm UTC
            for day in range(1, 6):
                for hour in range(13, 17):
                    availability.extend([day * 24 + hour, day * 24 + hour + 0.5])

        elif pattern_type == 2:
            # Mid-day overlap: Tue-Thu 10am-3pm UTC (GOOD for team formation)
            for day in range(2, 5):
                for hour in range(10, 15):
                    availability.extend([day * 24 + hour, day * 24 + hour + 0.5])

        elif pattern_type == 3:
            # Evening people: Mon-Wed 5pm-9pm UTC
            for day in range(1, 4):
                for hour in range(17, 21):
                    availability.extend([day * 24 + hour, day * 24 + hour + 0.5])

        else:
            # Weekend warriors: Sat-Sun 10am-6pm UTC
            for day in [6, 0]:  # Saturday and Sunday
                for hour in range(10, 18):
                    availability.extend([day * 24 + hour, day * 24 + hour + 0.5])

        return availability
