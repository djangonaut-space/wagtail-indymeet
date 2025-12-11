"""
Management command to create or update the Session Organizers group with required permissions.
"""

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import BaseCommand
from django.db import transaction
from django.db.models import Q

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

        with transaction.atomic():
            group, _ = Group.objects.get_or_create(name="Session Organizers")

            # Get all content types in a single query
            models = [model for model, _ in permissions_to_add]
            content_types = ContentType.objects.get_for_models(
                *models, for_concrete_models=False
            )

            # Build list of (content_type_id, codename) tuples for all permissions
            permission_lookups = [(content_types[Team].id, "form_team")]
            for model, perm_types in permissions_to_add:
                content_type = content_types[model]
                for perm_type in perm_types:
                    permission_lookups.append(
                        (content_type.id, f"{perm_type}_{model._meta.model_name}")
                    )

            permission_query = Q()
            for ct_id, codename in permission_lookups:
                permission_query |= Q(content_type_id=ct_id, codename=codename)

            permissions = Permission.objects.filter(permission_query)
            desired_permission_ids = set(permissions.values_list("id", flat=True))

            # Add the permissions
            GroupPermission = Group.permissions.through
            GroupPermission.objects.bulk_create(
                [
                    GroupPermission(group_id=group.id, permission_id=perm_id)
                    for perm_id in desired_permission_ids
                ],
                ignore_conflicts=True,
            )
            # Remove any extra permissions that shouldn't be there
            GroupPermission.objects.filter(group=group).exclude(
                permission_id__in=desired_permission_ids
            ).delete()

            self.stdout.write(
                self.style.SUCCESS(
                    f"Set up Session Organizers group with {len(desired_permission_ids)} "
                    "permissions."
                )
            )
