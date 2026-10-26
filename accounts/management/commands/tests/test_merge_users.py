from io import StringIO

import pytest
from django.contrib.auth.models import Group
from django.core import management
from django.core.management.base import CommandError

from accounts.factories import DiscordMemberFactory, UserFactory
from accounts.models import CustomUser, Link, MemberList
from home.factories import (
    SessionFactory,
    SessionMembershipFactory,
    UserSurveyResponseFactory,
    WaitlistFactory,
)
from home.models import SessionMembership


def run(*args: str) -> str:
    out = StringIO()
    management.call_command("merge_users", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
class TestMergeUsersCommand:
    def test_moves_related_rows_and_deletes_merged_user(self):
        keep = UserFactory.create()
        merge = UserFactory.create()
        membership = SessionMembershipFactory.create(user=merge)
        waitlist = WaitlistFactory.create(user=merge)
        response = UserSurveyResponseFactory.create(user=merge)

        run(keep.username, merge.username)

        assert not CustomUser.objects.filter(pk=merge.pk).exists()
        for obj in (membership, waitlist, response):
            obj.refresh_from_db()
            assert obj.user == keep

    def test_conflicting_rows_keep_the_kept_users_row(self):
        keep = UserFactory.create()
        merge = UserFactory.create()
        session = SessionFactory.create()
        kept_membership = SessionMembershipFactory.create(
            user=keep, session=session, team=None
        )
        SessionMembershipFactory.create(user=merge, session=session, team=None)

        output = run(keep.username, merge.username)

        assert list(SessionMembership.objects.filter(session=session)) == [
            kept_membership
        ]
        assert "home.SessionMembership" in output
        assert "Discarded" in output

    def test_fills_blank_profile_fields_from_merged_user(self):
        keep = UserFactory.create()
        discord_member = DiscordMemberFactory.create()
        merge = UserFactory.create(
            profile__github_username="octocat",
            profile__discord_username="Bazzan#1",
            profile__discord_member=discord_member,
            profile__bio="Hello",
        )

        run(keep.username, merge.username)

        profile = CustomUser.objects.get(pk=keep.pk).profile
        assert profile.github_username == "octocat"
        assert profile.discord_username == "Bazzan#1"
        assert profile.discord_member == discord_member
        assert profile.bio == "Hello"

    def test_kept_profile_values_win_over_merged_values(self):
        keep = UserFactory.create(profile__github_username="keeper")
        merge = UserFactory.create(
            profile__github_username="other", profile__bio="Merged bio"
        )

        output = run(keep.username, merge.username)

        profile = CustomUser.objects.get(pk=keep.pk).profile
        assert profile.github_username == "keeper"
        assert profile.bio == "Merged bio"
        assert "UserProfile.github_username='other'" in output

    def test_moves_profile_links(self):
        keep = UserFactory.create()
        merge = UserFactory.create()
        Link.objects.create(member=merge.profile, name="Site", url="https://a.example")

        run(keep.username, merge.username)

        assert list(keep.profile.links.values_list("name", flat=True)) == ["Site"]

    def test_creates_profile_when_kept_user_has_none(self):
        keep = UserFactory.create(profile=None)
        merge = UserFactory.create(profile__github_username="octocat")

        run(keep.username, merge.username)

        assert CustomUser.objects.get(pk=keep.pk).profile.github_username == "octocat"

    def test_moves_member_list_membership(self):
        keep = UserFactory.create()
        merge = UserFactory.create()
        member_list = MemberList.objects.create(name="List")
        member_list.members.add(merge)

        run(keep.username, merge.username)

        assert list(member_list.members.all()) == [keep]

    def test_merges_groups(self):
        keep = UserFactory.create()
        merge = UserFactory.create()
        group = Group.objects.create(name="Organizers")
        merge.groups.add(group)

        run(keep.username, merge.username)

        assert list(keep.groups.all()) == [group]

    def test_dry_run_changes_nothing(self):
        keep = UserFactory.create()
        merge = UserFactory.create()
        waitlist = WaitlistFactory.create(user=merge)

        output = run(keep.username, merge.username, "--dry-run")

        waitlist.refresh_from_db()
        assert waitlist.user == merge
        assert CustomUser.objects.filter(pk=merge.pk).exists()
        assert "Moved 1 home.Waitlist.user" in output
        assert "Dry run" in output

    def test_unknown_user_raises(self):
        keep = UserFactory.create()
        with pytest.raises(CommandError):
            run(keep.username, "missing")

    def test_same_user_raises(self):
        keep = UserFactory.create()
        with pytest.raises(CommandError):
            run(keep.username, keep.username)
