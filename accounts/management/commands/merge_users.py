from dataclasses import dataclass, field

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.db.models import Model

from accounts.models import Link, UserProfile

User = get_user_model()


PROFILE_FIELDS = (
    "pronouns",
    "bio",
    "bio_image",
    "github_username",
    "discord_username",
    "discord_member",
    "timezone",
)


class DryRunRollback(Exception):
    """Raised to roll back the merge transaction after a dry run."""


@dataclass
class MergeReport:
    moved: dict[str, int] = field(default_factory=dict)
    conflicts: list[str] = field(default_factory=list)


class Command(BaseCommand):
    help = (
        "Merge one user account into another. Everything that references the "
        "merged account is re-pointed at the kept account, then the merged account "
        "is deleted. Where both accounts have a row that can't coexist (for example "
        "membership in the same session), the kept account's row wins and the merged "
        "account's row is discarded."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("keep", help="Username of the account to keep.")
        parser.add_argument(
            "merge", help="Username of the account to merge in and delete."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change, then roll everything back.",
        )

    def handle(self, *args, **options) -> None:
        keep = self.get_user(options["keep"])
        merge = self.get_user(options["merge"])
        if keep.pk == merge.pk:
            raise CommandError("The accounts to keep and to merge must differ.")

        dry_run = options["dry_run"]
        try:
            with transaction.atomic():
                report = self.merge_users(keep, merge)
                if dry_run:
                    raise DryRunRollback
        except DryRunRollback:
            pass

        for label, count in report.moved.items():
            self.stdout.write(f"Moved {count} {label}")
        for conflict in report.conflicts:
            self.stdout.write(self.style.WARNING(f"Discarded: {conflict}"))
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run: no changes were saved."))
        else:
            self.stdout.write(
                self.style.SUCCESS(f"Merged {merge.username} into {keep.username}.")
            )

    def get_user(self, username: str) -> Model:
        try:
            return User.objects.get(username=username)
        except User.DoesNotExist:
            raise CommandError(f"No user with username {username!r}.")

    def merge_users(self, keep: Model, merge: Model) -> MergeReport:
        """Re-point every reference to ``merge`` at ``keep``, then delete ``merge``."""
        report = MergeReport()
        profile_values, links = self.pop_profile(merge)
        for relation in User._meta.related_objects:
            if relation.related_model is UserProfile:
                continue
            if relation.many_to_many:
                if relation.through._meta.auto_created:
                    self.merge_many_to_many(relation, keep, merge, report)
                continue
            self.merge_foreign_key(relation, keep, merge, report)

        keep.groups.add(*merge.groups.all())
        keep.user_permissions.add(*merge.user_permissions.all())
        merge.delete()
        self.merge_profile(keep, profile_values, links, report)
        return report

    def pop_profile(self, merge: Model) -> tuple[dict, list[Link]]:
        """
        Detach the merged user's profile data and delete the profile.

        The profile is deleted up front because the Discord fields are unique, so
        the values can't be copied onto the kept profile while both exist.
        """
        profile = UserProfile.objects.filter(user=merge).first()
        if profile is None:
            return {}, []
        values = {name: getattr(profile, name) for name in PROFILE_FIELDS}
        links = list(profile.links.all())
        profile.delete()
        return values, links

    def merge_profile(
        self, keep: Model, values: dict, links: list[Link], report: MergeReport
    ) -> None:
        """Fill blank profile fields on ``keep`` and carry over profile links."""
        profile, _ = UserProfile.objects.get_or_create(user=keep)
        filled = []
        for name, value in values.items():
            if value and not getattr(profile, name):
                setattr(profile, name, value)
                filled.append(name)
            elif value and value != getattr(profile, name):
                report.conflicts.append(f"UserProfile.{name}={value!r}")
        if filled:
            profile.save(update_fields=filled)
            report.moved["accounts.UserProfile fields: " + ", ".join(filled)] = len(
                filled
            )
        for link in links:
            Link.objects.create(
                member=profile, name=link.name, url=link.url, sort_order=link.sort_order
            )
        if links:
            report.moved["accounts.Link"] = len(links)

    def merge_foreign_key(self, relation, keep, merge, report: MergeReport) -> None:
        model = relation.related_model
        field_name = relation.field.name
        for pk in list(
            model._base_manager.filter(**{field_name: merge}).values_list(
                "pk", flat=True
            )
        ):
            try:
                with transaction.atomic():
                    model._base_manager.filter(pk=pk).update(**{field_name: keep})
            except IntegrityError:
                report.conflicts.append(f"{model._meta.label} pk={pk}")
            else:
                label = f"{model._meta.label}.{field_name}"
                report.moved[label] = report.moved.get(label, 0) + 1

    def merge_many_to_many(self, relation, keep, merge, report: MergeReport) -> None:
        model = relation.related_model
        accessor = relation.field.name
        for obj in model._base_manager.filter(**{accessor: merge}):
            getattr(obj, accessor).add(keep)
            getattr(obj, accessor).remove(merge)
            label = f"{model._meta.label}.{accessor}"
            report.moved[label] = report.moved.get(label, 0) + 1
