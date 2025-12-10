"""
Management command to create or update the Session Organizers group with required permissions.
"""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import BaseCommand

from accounts.models import CustomUser, UserAvailability, UserProfile
from home.models import (
    Project,
    ResourceLink,
    Session,
    SessionMembership,
    Survey,
    Team,
    UserQuestionResponse,
    UserSurveyResponse,
    Waitlist,
)


class Command(BaseCommand):
    help = "Create or update the Session Organizers group with required permissions."

    def handle(self, *args, **options) -> None:
        group, created = Group.objects.get_or_create(name="Session Organizers")
        group.permissions.clear()

        permissions_to_add = [
            (CustomUser, ["view"]),
            (ResourceLink, ["view", "add"]),
            (Session, ["view", "add"]),
            (Survey, ["view", "add"]),
            (UserQuestionResponse, ["view", "add"]),
            (UserSurveyResponse, ["view", "add"]),
            (Waitlist, ["view", "add"]),
            (Team, ["view", "add"]),
            (Project, ["view", "add"]),
            (UserProfile, ["view", "add", "change"]),
            (UserAvailability, ["view", "add", "change"]),
            (SessionMembership, ["view", "add", "change"]),
        ]

        permission_count = 0
        for model, perm_types in permissions_to_add:
            content_type = ContentType.objects.get_for_model(model)
            for perm_type in perm_types:
                permission = Permission.objects.get(
                    content_type=content_type,
                    codename=f"{perm_type}_{model._meta.model_name}",
                )
                group.permissions.add(permission)
                permission_count += 1

        team_ct = ContentType.objects.get_for_model(Team)
        form_team_perm = Permission.objects.get(
            content_type=team_ct, codename="form_team"
        )
        group.permissions.add(form_team_perm)
        permission_count += 1

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} Session Organizers group with {permission_count} permissions."
            )
        )
