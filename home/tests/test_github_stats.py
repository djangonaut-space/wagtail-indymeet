from datetime import date, datetime
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from github import GithubException

from accounts.factories import UserFactory
from accounts.models import UserProfile
from home.factories import (
    ProjectFactory,
    SessionFactory,
    SessionMembershipFactory,
    TeamFactory,
)
from home.models.session import SessionMembership
from home.services.github_stats import (
    Author,
    GitHubStatsCollector,
    Issue,
    PR,
    StatsReport,
    TeamReport,
    TeamScope,
)

User = get_user_model()


def _build_mock_pr(
    *,
    number: int,
    login: str = "testuser",
    created_at=None,
    merged_at=None,
    state: str = "open",
    repo: str = "test-org/test-repo",
):
    """Build a mock search-result PR item suitable for ``collect_all_stats``."""
    mock_user = Mock()
    mock_user.login = login

    mock_pr = Mock()
    mock_pr.title = f"PR {number}"
    mock_pr.number = number
    mock_pr.html_url = f"https://github.com/{repo}/pull/{number}"
    mock_pr.user = mock_user
    mock_pr.created_at = created_at or date(2024, 1, 15)
    mock_pr.state = state
    mock_pr.repository_url = f"https://api.github.com/repos/{repo}"
    mock_pr.pull_request = Mock(merged_at=merged_at)
    return mock_pr


def _build_mock_issue(
    *,
    number: int,
    login: str = "testuser",
    created_at=None,
    state: str = "open",
    repo: str = "test-org/test-repo",
):
    mock_user = Mock()
    mock_user.login = login

    mock_issue = Mock()
    mock_issue.title = f"Issue {number}"
    mock_issue.number = number
    mock_issue.html_url = f"https://github.com/{repo}/issues/{number}"
    mock_issue.user = mock_user
    mock_issue.created_at = created_at or date(2024, 1, 20)
    mock_issue.state = state
    mock_issue.repository_url = f"https://api.github.com/repos/{repo}"
    return mock_issue


class GitHubStatsCollectorTests(SimpleTestCase):
    def setUp(self):
        self.mock_token = "ghp_test_token"
        self.author = Author(github_username="testuser", name="Test User")
        self.scope = TeamScope(
            scope_term="repo:test-org/test-repo",
            members=(self.author,),
            label="Team Alpha - Django",
        )

    @patch("home.services.github_stats.Github")
    def test_init_with_token(self, mock_github_class):
        collector = GitHubStatsCollector(self.mock_token)
        mock_github_class.assert_called_once()
        self.assertEqual(mock_github_class.call_args.args[0], self.mock_token)
        self.assertIsNotNone(collector.github)

    @patch("home.services.github_stats.Github")
    def test_init_with_settings_token(self, mock_github_class):
        with override_settings(GITHUB_TOKEN="settings_token"):
            GitHubStatsCollector()
            mock_github_class.assert_called_once()
            self.assertEqual(mock_github_class.call_args.args[0], "settings_token")

    @patch("home.services.github_stats.Github")
    def test_init_disables_retries_for_loud_rate_limit_failure(self, mock_github_class):
        """A total=0 urllib3 Retry is passed so rate-limit 403s raise instead of sleep."""
        GitHubStatsCollector(self.mock_token)
        retry = mock_github_class.call_args.kwargs["retry"]
        self.assertEqual(retry.total, 0)

    @patch("home.services.github_stats.Github")
    def test_init_without_token_raises_error(self, mock_github_class):
        with override_settings(GITHUB_TOKEN=None):
            with self.assertRaises(ValueError) as context:
                GitHubStatsCollector()
            self.assertIn("GitHub token is required", str(context.exception))

    @patch("home.services.github_stats.Github")
    def test_collect_all_stats_returns_pr_and_issue(self, mock_github_class):
        mock_pr = _build_mock_pr(
            number=123,
            login="testuser",
            created_at=date(2024, 1, 15),
            merged_at=datetime(2024, 1, 16, 12, 0, 0),
            state="open",
        )
        mock_issue = _build_mock_issue(
            number=456, login="testuser", created_at=date(2024, 1, 20)
        )

        mock_github_instance = mock_github_class.return_value
        # created-PR query, merged-PR query (empty), issue query
        mock_github_instance.search_issues.side_effect = [
            [mock_pr],
            [],
            [mock_issue],
        ]

        collector = GitHubStatsCollector(self.mock_token)
        report = collector.collect_all_stats(
            scopes=[self.scope],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        self.assertIsInstance(report, StatsReport)
        self.assertEqual(len(report.teams), 1)
        team = report.teams[0]
        self.assertEqual(team.label, "Team Alpha - Django")
        self.assertEqual(team.scope_term, "repo:test-org/test-repo")
        self.assertEqual(len(team.prs), 1)
        self.assertEqual(len(team.issues), 1)
        self.assertEqual(team.prs[0].merged_at, date(2024, 1, 16))
        self.assertEqual(team.prs[0].repo, "test-org/test-repo")
        # Author carries the real display name from the scope, not the login.
        self.assertEqual(team.prs[0].author.name, "Test User")
        self.assertEqual(team.issues[0].author.name, "Test User")

    @patch("home.services.github_stats.Github")
    def test_collect_all_stats_runs_created_merged_and_issue_queries(
        self, mock_github_class
    ):
        mock_github_instance = mock_github_class.return_value
        mock_github_instance.search_issues.side_effect = [[], [], []]

        collector = GitHubStatsCollector(self.mock_token)
        collector.collect_all_stats(
            scopes=[self.scope],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        self.assertEqual(mock_github_instance.search_issues.call_count, 3)
        created_pr_query = mock_github_instance.search_issues.call_args_list[0].args[0]
        merged_pr_query = mock_github_instance.search_issues.call_args_list[1].args[0]
        issue_query = mock_github_instance.search_issues.call_args_list[2].args[0]

        self.assertIn("repo:test-org/test-repo", created_pr_query)
        self.assertIn("author:testuser", created_pr_query)
        self.assertIn("type:pr", created_pr_query)
        self.assertIn("created:2024-01-01..2024-01-31", created_pr_query)

        self.assertIn("repo:test-org/test-repo", merged_pr_query)
        self.assertIn("author:testuser", merged_pr_query)
        self.assertIn("type:pr", merged_pr_query)
        self.assertIn("merged:2024-01-01..2024-01-31", merged_pr_query)

        self.assertIn("repo:test-org/test-repo", issue_query)
        self.assertIn("type:issue", issue_query)
        self.assertIn("created:2024-01-01..2024-01-31", issue_query)

    @patch("home.services.github_stats.Github")
    def test_collect_all_stats_deduplicates_pr_across_created_and_merged(
        self, mock_github_class
    ):
        """A PR returned by both the ``created:`` and ``merged:`` query is counted once."""
        mock_pr = _build_mock_pr(
            number=42,
            login="testuser",
            created_at=date(2024, 1, 15),
            merged_at=datetime(2024, 1, 18, 12, 0, 0),
            state="closed",
        )

        mock_github_instance = mock_github_class.return_value
        # Same PR returned by the created query AND the merged query, plus empty issues.
        mock_github_instance.search_issues.side_effect = [[mock_pr], [mock_pr], []]

        collector = GitHubStatsCollector(self.mock_token)
        report = collector.collect_all_stats(
            scopes=[self.scope],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        prs = report.teams[0].prs
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0].number, 42)
        self.assertTrue(prs[0].is_merged)

    @patch("home.services.github_stats.Github")
    def test_collect_all_stats_captures_pr_merged_but_not_created_in_window(
        self, mock_github_class
    ):
        """PRs created before the window but merged inside it are still captured."""
        mock_pr = _build_mock_pr(
            number=7,
            login="testuser",
            created_at=date(2023, 12, 28),
            merged_at=datetime(2024, 1, 5, 10, 0, 0),
            state="closed",
        )

        mock_github_instance = mock_github_class.return_value
        # The created:<window> query doesn't find it; the merged:<window> query does.
        mock_github_instance.search_issues.side_effect = [[], [mock_pr], []]

        collector = GitHubStatsCollector(self.mock_token)
        report = collector.collect_all_stats(
            scopes=[self.scope],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        prs = report.teams[0].prs
        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0].number, 7)
        self.assertTrue(prs[0].is_merged)

    @patch("home.services.github_stats.Github")
    def test_collect_all_stats_runs_one_query_per_member_per_qualifier(
        self, mock_github_class
    ):
        """GitHub Search rejects OR'd author clauses (422), so we query per member."""
        scope = TeamScope(
            scope_term="repo:test-org/test-repo",
            members=(
                Author(github_username="alice", name="Alice A"),
                Author(github_username="bob", name="Bob B"),
            ),
            label="Team Alpha",
        )
        mock_github_instance = mock_github_class.return_value
        mock_github_instance.search_issues.return_value = []

        collector = GitHubStatsCollector(self.mock_token)
        collector.collect_all_stats(
            scopes=[scope],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        # 2 members × (created PR + merged PR + issue) = 6 queries.
        self.assertEqual(mock_github_instance.search_issues.call_count, 6)
        queries = [c.args[0] for c in mock_github_instance.search_issues.call_args_list]
        for q in queries:
            self.assertNotIn(" OR ", q)
        self.assertTrue(any("author:alice" in q for q in queries))
        self.assertTrue(any("author:bob" in q for q in queries))

    @patch("home.services.github_stats.Github")
    def test_collect_all_stats_runs_per_scope(self, mock_github_class):
        """Two scopes run their own created+merged+issue query sets."""
        scope_a = TeamScope(
            scope_term="repo:org-a/repo-a",
            members=(Author(github_username="alice", name="Alice A"),),
        )
        scope_b = TeamScope(
            scope_term="org:org-b",
            members=(Author(github_username="bob", name="Bob B"),),
        )

        mock_github_instance = mock_github_class.return_value
        mock_github_instance.search_issues.return_value = []

        collector = GitHubStatsCollector(self.mock_token)
        collector.collect_all_stats(
            scopes=[scope_a, scope_b],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        # 3 queries per scope (created PR, merged PR, issues) × 2 scopes = 6.
        self.assertEqual(mock_github_instance.search_issues.call_count, 6)
        queries = [c.args[0] for c in mock_github_instance.search_issues.call_args_list]
        self.assertTrue(
            any("repo:org-a/repo-a" in q and "author:alice" in q for q in queries)
        )
        self.assertTrue(any("org:org-b" in q and "author:bob" in q for q in queries))

    def test_to_date(self):
        """Test _to_date helper method."""
        collector = GitHubStatsCollector(self.mock_token)

        # Test datetime conversion
        dt = datetime(2024, 1, 15, 12, 0, 0)
        self.assertEqual(collector._to_date(dt), date(2024, 1, 15))

        # Test date pass-through
        d = date(2024, 1, 15)
        self.assertEqual(collector._to_date(d), d)

        # Test None
        self.assertIsNone(collector._to_date(None))


class DataClassesTests(SimpleTestCase):
    def setUp(self):
        self.author = Author(github_username="test", name="Test")

    def test_pr_properties(self):
        """Test PR property methods (is_open, is_merged, is_closed)."""
        # Open PR
        pr_open = PR(
            title="t",
            number=1,
            url="u",
            author=self.author,
            created_at=date(2024, 1, 1),
            merged_at=None,
            state="open",
            repo="r",
        )
        self.assertTrue(pr_open.is_open)
        self.assertFalse(pr_open.is_merged)
        self.assertFalse(pr_open.is_closed)

        # Merged PR
        pr_merged = PR(
            title="t",
            number=1,
            url="u",
            author=self.author,
            created_at=date(2024, 1, 1),
            merged_at=date(2024, 1, 2),
            state="closed",
            repo="r",
        )
        self.assertFalse(pr_merged.is_open)
        self.assertTrue(pr_merged.is_merged)
        self.assertFalse(pr_merged.is_closed)

        # Closed PR
        pr_closed = PR(
            title="t",
            number=1,
            url="u",
            author=self.author,
            created_at=date(2024, 1, 1),
            merged_at=None,
            state="closed",
            repo="r",
        )
        self.assertFalse(pr_closed.is_open)
        self.assertFalse(pr_closed.is_merged)
        self.assertTrue(pr_closed.is_closed)

    def test_issue_properties(self):
        """Test Issue property methods."""
        issue = Issue(
            title="t",
            number=1,
            url="u",
            author=self.author,
            created_at=date(2024, 1, 1),
            state="open",
            repo="r",
        )
        self.assertTrue(issue.is_open)

        issue_closed = Issue(
            title="t",
            number=1,
            url="u",
            author=self.author,
            created_at=date(2024, 1, 1),
            state="closed",
            repo="r",
        )
        self.assertFalse(issue_closed.is_open)


class StatsReportTests(SimpleTestCase):
    def setUp(self):
        self.author1 = Author(github_username="user1", name="User One")
        self.author2 = Author(github_username="user2", name="User Two")

        self.pr_open = PR(
            title="Open PR",
            number=1,
            url="https://github.com/org/repo/pull/1",
            author=self.author1,
            created_at=date(2024, 1, 10),
            merged_at=None,
            state="open",
            repo="org/repo",
        )

        self.pr_merged = PR(
            title="Merged PR",
            number=2,
            url="https://github.com/org/repo/pull/2",
            author=self.author2,
            created_at=date(2024, 1, 5),
            merged_at=date(2024, 1, 15),
            state="closed",
            repo="org/repo",
        )

        self.pr_closed = PR(
            title="Closed PR",
            number=3,
            url="https://github.com/org/repo/pull/3",
            author=self.author1,
            created_at=date(2024, 1, 8),
            merged_at=None,
            state="closed",
            repo="org/repo",
        )

        self.issue_open = Issue(
            title="Open Issue",
            number=10,
            url="https://github.com/org/repo/issues/10",
            author=self.author1,
            created_at=date(2024, 1, 12),
            state="open",
            repo="org/repo",
        )

        self.team_report = TeamReport(
            label="Team A - Project X",
            scope_term="repo:org/repo",
            prs=[self.pr_open, self.pr_merged, self.pr_closed],
            issues=[self.issue_open],
        )
        self.report = StatsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            teams=[self.team_report],
        )

    def test_team_open_prs(self):
        self.assertEqual([pr.title for pr in self.team_report.open_prs], ["Open PR"])

    def test_team_merged_prs(self):
        self.assertEqual(
            [pr.title for pr in self.team_report.merged_prs], ["Merged PR"]
        )

    def test_team_closed_prs(self):
        self.assertEqual(
            [pr.title for pr in self.team_report.closed_prs], ["Closed PR"]
        )

    def test_team_open_issues(self):
        self.assertEqual(
            [i.title for i in self.team_report.open_issues], ["Open Issue"]
        )

    def test_authors(self):
        authors = self.report.authors
        author_names = {author.name for author in authors}
        self.assertEqual(author_names, {"User One", "User Two"})

    def test_count_methods(self):
        self.assertEqual(self.report.count_open_prs(), 1)
        self.assertEqual(self.report.count_merged_prs(), 1)
        self.assertEqual(self.report.count_closed_prs(), 1)
        self.assertEqual(self.report.count_open_issues(), 1)

    def test_count_methods_sum_across_teams(self):
        second_team = TeamReport(
            label="Team B",
            scope_term="repo:org/other",
            prs=[self.pr_open],
        )
        report = StatsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            teams=[self.team_report, second_team],
        )
        self.assertEqual(report.count_open_prs(), 2)
        self.assertEqual(report.count_merged_prs(), 1)

    def test_has_activity(self):
        self.assertTrue(self.report.has_activity)
        empty = StatsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            teams=[TeamReport(label="Empty", scope_term="repo:o/r")],
        )
        self.assertFalse(empty.has_activity)

    def test_pr_is_closed(self):
        """Test that is_closed property correctly identifies closed PRs."""
        self.assertTrue(self.pr_closed.is_closed)
        self.assertFalse(self.pr_merged.is_closed)  # merged PR should not be closed
        self.assertFalse(self.pr_open.is_closed)  # open PR should not be closed


class CollectStatsViewIntegrationTests(TestCase):
    """Integration tests for the collect_stats_view admin interface."""

    def setUp(self):
        self.staff_user = UserFactory.create(is_staff=True, is_superuser=True)
        self.client = Client()
        self.client.force_login(self.staff_user)

        self.session = SessionFactory.create(title="Test Session")
        self.project = ProjectFactory.create(
            name="Django",
            url="https://github.com/test-org/test-repo",
        )
        self.session.available_projects.add(self.project)

        self.team = TeamFactory.create(
            session=self.session, project=self.project, name="Team Alpha"
        )

        self.djangonaut1 = UserFactory.create(first_name="Jane", last_name="Doe")
        UserProfile.objects.filter(user=self.djangonaut1).update(
            github_username="djangonaut1"
        )
        SessionMembershipFactory.create(
            session=self.session,
            user=self.djangonaut1,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
        )

        self.djangonaut2 = UserFactory.create(first_name="John", last_name="Smith")
        UserProfile.objects.filter(user=self.djangonaut2).update(
            github_username="djangonaut2"
        )
        SessionMembershipFactory.create(
            session=self.session,
            user=self.djangonaut2,
            team=self.team,
            role=SessionMembership.DJANGONAUT,
        )

        self.url = reverse(
            "admin:session_collect_stats", kwargs={"session_id": self.session.id}
        )

    @override_settings(GITHUB_TOKEN="test_token")
    @patch("home.views.sessions.GitHubStatsCollector")
    def test_displays_mixed_pr_states(self, mock_collector_class):
        """Verify view correctly displays open, merged, and closed PRs."""
        mock_collector = Mock()
        mock_collector_class.return_value = mock_collector
        mock_collector.collect_all_stats.return_value = StatsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            teams=[
                TeamReport(
                    label="Team Alpha - Django",
                    scope_term="repo:test-org/test-repo",
                    prs=[
                        PR(
                            title="Open PR",
                            number=1,
                            url="https://github.com/test-org/test-repo/pull/1",
                            author=Author(
                                github_username="djangonaut1", name="Jane Doe"
                            ),
                            created_at=date(2024, 1, 15),
                            merged_at=None,
                            state="open",
                            repo="test-org/test-repo",
                        ),
                        PR(
                            title="Merged PR",
                            number=2,
                            url="https://github.com/test-org/test-repo/pull/2",
                            author=Author(
                                github_username="djangonaut2", name="John Smith"
                            ),
                            created_at=date(2024, 1, 10),
                            merged_at=date(2024, 1, 20),
                            state="closed",
                            repo="test-org/test-repo",
                        ),
                        PR(
                            title="Closed PR",
                            number=3,
                            url="https://github.com/test-org/test-repo/pull/3",
                            author=Author(
                                github_username="djangonaut1", name="Jane Doe"
                            ),
                            created_at=date(2024, 1, 12),
                            merged_at=None,
                            state="closed",
                            repo="test-org/test-repo",
                        ),
                    ],
                    issues=[
                        Issue(
                            title="Test Issue",
                            number=10,
                            url="https://github.com/test-org/test-repo/issues/10",
                            author=Author(
                                github_username="djangonaut1", name="Jane Doe"
                            ),
                            created_at=date(2024, 1, 18),
                            state="open",
                            repo="test-org/test-repo",
                        ),
                    ],
                ),
            ],
        )

        response = self.client.post(
            self.url,
            {"start_date": "2024-01-01", "end_date": "2024-01-31"},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertIn("🎉 Merged Pull Requests", content)
        self.assertIn("🚧 Closed Pull Requests", content)
        self.assertIn("✨ Open Pull Requests", content)
        self.assertIn("✏️ Issues", content)

        # The collector was called once with a list of TeamScopes derived from
        # the session's teams, not a flat repo/username list.
        mock_collector.collect_all_stats.assert_called_once()
        call_kwargs = mock_collector.collect_all_stats.call_args.kwargs
        self.assertEqual(call_kwargs["start_date"], date(2024, 1, 1))
        self.assertEqual(call_kwargs["end_date"], date(2024, 1, 31))
        scopes = call_kwargs["scopes"]
        self.assertEqual(len(scopes), 1)
        scope = scopes[0]
        self.assertEqual(scope.scope_term, "repo:test-org/test-repo")
        self.assertEqual(
            {m.github_username for m in scope.members},
            {"djangonaut1", "djangonaut2"},
        )
        self.assertEqual(
            {m.name for m in scope.members},
            {"Jane Doe", "John Smith"},
        )

    @override_settings(GITHUB_TOKEN="test_token")
    @patch("home.views.sessions.GitHubStatsCollector")
    def test_uses_org_scope_when_project_monitors_whole_org(self, mock_collector_class):
        self.project.monitor_all_organization_repos = True
        self.project.save()

        mock_collector = Mock()
        mock_collector_class.return_value = mock_collector
        mock_collector.collect_all_stats.return_value = StatsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            teams=[],
        )

        self.client.post(
            self.url,
            {"start_date": "2024-01-01", "end_date": "2024-01-31"},
        )

        scope = mock_collector.collect_all_stats.call_args.kwargs["scopes"][0]
        self.assertEqual(scope.scope_term, "org:test-org")

    @override_settings(GITHUB_TOKEN="test_token")
    @patch("home.views.sessions.GitHubStatsCollector")
    def test_hides_empty_sections(self, mock_collector_class):
        """Verify sections without data are not displayed."""
        mock_collector = Mock()
        mock_collector_class.return_value = mock_collector
        mock_collector.collect_all_stats.return_value = StatsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            teams=[
                TeamReport(
                    label="Team Alpha - Django",
                    scope_term="repo:test-org/test-repo",
                    prs=[
                        PR(
                            title="Closed PR",
                            number=1,
                            url="https://github.com/test-org/test-repo/pull/1",
                            author=Author(
                                github_username="djangonaut1", name="Jane Doe"
                            ),
                            created_at=date(2024, 1, 15),
                            merged_at=None,
                            state="closed",
                            repo="test-org/test-repo",
                        ),
                    ],
                ),
            ],
        )

        response = self.client.post(
            self.url,
            {"start_date": "2024-01-01", "end_date": "2024-01-31"},
        )

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()

        self.assertIn("🚧 Closed Pull Requests", content)
        self.assertNotIn("🎉 Merged Pull Requests", content)
        self.assertNotIn("✨ Open Pull Requests", content)
        self.assertNotIn("✏️ Issues", content)

    @override_settings(GITHUB_TOKEN="test_token")
    def test_form_display(self):
        """GET request shows the date selection form."""
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("start_date", content)
        self.assertIn("end_date", content)
        self.assertIn(self.session.title, content)

    @override_settings(GITHUB_TOKEN="test_token")
    def test_redirects_when_session_has_no_teams_with_github_projects(self):
        """Redirects with error when no team has a GitHub-backed project."""
        self.session.teams.all().delete()

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        messages = list(get_messages(response.wsgi_request))
        self.assertIn(
            "No teams with GitHub projects",
            str(messages[0]),
        )

    @override_settings(GITHUB_TOKEN="test_token")
    @patch("home.views.sessions.GitHubStatsCollector")
    def test_github_api_error_redirects_with_message(self, mock_collector_class):
        """Redirects with error message when GitHub API raises an exception."""
        mock_collector = Mock()
        mock_collector_class.return_value = mock_collector
        mock_collector.collect_all_stats.side_effect = GithubException(
            500, "API error", None
        )

        response = self.client.post(
            self.url,
            {"start_date": "2024-01-01", "end_date": "2024-01-31"},
        )

        self.assertEqual(response.status_code, 302)
        msgs = list(get_messages(response.wsgi_request))
        self.assertIn("GitHub API error", str(msgs[0]))

    @override_settings(GITHUB_TOKEN="test_token")
    def test_invalid_form_redisplays_form(self):
        """POST with invalid dates re-renders the form with errors."""
        response = self.client.post(
            self.url,
            {"start_date": "", "end_date": ""},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "start_date")

    @override_settings(GITHUB_TOKEN="test_token")
    def test_redirects_when_no_github_usernames(self):
        """Redirects with message when no team Djangonauts have GitHub usernames."""
        UserProfile.objects.filter(
            user__in=[self.djangonaut1, self.djangonaut2]
        ).update(github_username="")

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 302)
        messages = list(get_messages(response.wsgi_request))
        self.assertIn("No teams with GitHub projects", str(messages[0]))
