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
        user = User.objects.create_user(
            username=os.environ["PLAYWRIGHT_TEST_USERNAME"],
            password=os.environ["PLAYWRIGHT_TEST_PASSWORD"],
            first_name="Playwright",
            last_name="Test",
            is_staff=True,
            is_superuser=False,
        )
        user.groups.add(Group.objects.get(name="Editors"))
        self.stdout.write("Created playwright test user - %s." % user.username)
