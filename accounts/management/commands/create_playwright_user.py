"""
Management utility to create playwright test user.
"""

import os

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import BaseCommand

User = get_user_model()


class Command(BaseCommand):
    help = "Used to create a playwright test user."

    def handle(self, *args, **options):
        user, _ = User.objects.get_or_create(
            username=os.environ["PLAYWRIGHT_TEST_USERNAME"],
            first_name="Playwright",
            last_name="Test",
            is_staff=True,
            is_superuser=False,
        )
        user.set_password(os.environ["PLAYWRIGHT_TEST_PASSWORD"])
        user.save()
        user.groups.add(Group.objects.get_or_create(name="Editors")[0])
        self.stdout.write("Created playwright test user - %s." % user.username)
