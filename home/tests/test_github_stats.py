from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.factories import ProfileFactory, UserFactory
from home.factories import SessionFactory, SessionMembershipFactory
from home.services.github_stats import (
    Author,
    GitHubStatsCollector,
    Issue,
    PR,
    StatsReport,
)
from home.services.report_formatter import ReportFormatter

User = get_user_model()


class GitHubStatsCollectorTests(TestCase):
    def setUp(self):
        self.mock_github = Mock()
        self.mock_token = "ghp_test_token"

    @patch("home.services.github_stats.Github")
    def test_init_with_token(self, mock_github_class):
        collector = GitHubStatsCollector(self.mock_token)
        mock_github_class.assert_called_once_with(self.mock_token)
        self.assertIsNotNone(collector.github)

    @patch("home.services.github_stats.Github")
    def test_init_with_settings_token(self, mock_github_class):
        with override_settings(GITHUB_TOKEN="settings_token"):
            collector = GitHubStatsCollector()
            mock_github_class.assert_called_once_with("settings_token")

    @patch("home.services.github_stats.Github")
    def test_init_without_token_raises_error(self, mock_github_class):
        with override_settings(GITHUB_TOKEN=None):
            with self.assertRaises(ValueError) as context:
                GitHubStatsCollector()
            self.assertIn("GitHub token is required", str(context.exception))

    @patch("home.services.github_stats.Github")
    def test_collect_prs_for_repo(self, mock_github_class):
        mock_user = Mock()
        mock_user.login = "testuser"
        mock_user.name = "Test User"

        mock_pr = Mock()
        mock_pr.title = "Test PR"
        mock_pr.number = 123
        mock_pr.html_url = "https://github.com/org/repo/pull/123"
        mock_pr.user = mock_user
        mock_pr.created_at = date(2024, 1, 15)
        mock_pr.state = "open"

        mock_github_instance = mock_github_class.return_value
        mock_github_instance.search_issues.return_value = [mock_pr]

        collector = GitHubStatsCollector(self.mock_token)
        collector.github = mock_github_instance

        prs = collector.collect_prs_for_repo(
            owner="org",
            repo_name="repo",
            usernames=["testuser"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        self.assertEqual(len(prs), 1)
        self.assertEqual(prs[0].title, "Test PR")
        self.assertEqual(prs[0].number, 123)
        self.assertEqual(prs[0].author.github_username, "testuser")
        self.assertEqual(prs[0].state, "open")
        self.assertEqual(prs[0].repo, "org/repo")

    @patch("home.services.github_stats.Github")
    def test_collect_issues_for_repo(self, mock_github_class):
        mock_user = Mock()
        mock_user.login = "testuser"
        mock_user.name = "Test User"

        mock_issue = Mock()
        mock_issue.title = "Test Issue"
        mock_issue.number = 456
        mock_issue.html_url = "https://github.com/org/repo/issues/456"
        mock_issue.user = mock_user
        mock_issue.created_at = date(2024, 1, 20)
        mock_issue.state = "open"

        mock_github_instance = mock_github_class.return_value
        mock_github_instance.search_issues.return_value = [mock_issue]

        collector = GitHubStatsCollector(self.mock_token)
        collector.github = mock_github_instance

        issues = collector.collect_issues_for_repo(
            owner="org",
            repo_name="repo",
            usernames=["testuser"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].title, "Test Issue")
        self.assertEqual(issues[0].number, 456)
        self.assertEqual(issues[0].author.github_username, "testuser")
        self.assertEqual(issues[0].state, "open")

    @patch("home.services.github_stats.Github")
    def test_get_repos_from_config_wildcard(self, mock_github_class):
        mock_repo1 = Mock()
        mock_repo1.name = "repo1"
        mock_repo2 = Mock()
        mock_repo2.name = "repo2"

        mock_org = Mock()
        mock_org.get_repos.return_value = [mock_repo1, mock_repo2]

        mock_github_instance = mock_github_class.return_value
        mock_github_instance.get_organization.return_value = mock_org

        collector = GitHubStatsCollector(self.mock_token)
        collector.github = mock_github_instance

        repos = collector._get_repos_from_config("test-org", ["*"])

        self.assertEqual(repos, ["repo1", "repo2"])
        mock_org.get_repos.assert_called_once_with(type="sources")

    @patch("home.services.github_stats.Github")
    def test_get_repos_from_config_specific(self, mock_github_class):
        collector = GitHubStatsCollector(self.mock_token)
        repos = collector._get_repos_from_config("test-org", ["repo1", "repo2"])
        self.assertEqual(repos, ["repo1", "repo2"])

    @patch("home.services.github_stats.Github")
    def test_collect_all_stats(self, mock_github_class):
        mock_user = Mock()
        mock_user.login = "testuser"
        mock_user.name = "Test User"

        mock_repo = Mock()
        mock_repo.full_name = "test-org/test-repo"

        mock_pr = Mock()
        mock_pr.title = "Test PR"
        mock_pr.number = 123
        mock_pr.html_url = "https://github.com/test-org/test-repo/pull/123"
        mock_pr.user = mock_user
        mock_pr.created_at = date(2024, 1, 15)
        mock_pr.state = "open"
        mock_pr.repository = mock_repo

        mock_issue = Mock()
        mock_issue.title = "Test Issue"
        mock_issue.number = 456
        mock_issue.html_url = "https://github.com/test-org/test-repo/issues/456"
        mock_issue.user = mock_user
        mock_issue.created_at = date(2024, 1, 20)
        mock_issue.state = "open"
        mock_issue.repository = mock_repo

        mock_github_instance = mock_github_class.return_value
        mock_github_instance.search_issues.side_effect = [[mock_pr], [mock_issue]]

        collector = GitHubStatsCollector(self.mock_token)
        collector.github = mock_github_instance

        report = collector.collect_all_stats(
            repos=[{"owner": "test-org", "repos": ["test-repo"]}],
            usernames=["testuser"],
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        self.assertIsInstance(report, StatsReport)
        self.assertEqual(len(report.prs), 1)
        self.assertEqual(len(report.issues), 1)
        self.assertEqual(report.count_open_prs(), 1)
        self.assertEqual(report.count_open_issues(), 1)


class StatsReportTests(TestCase):
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

        self.issue_open = Issue(
            title="Open Issue",
            number=10,
            url="https://github.com/org/repo/issues/10",
            author=self.author1,
            created_at=date(2024, 1, 12),
            state="open",
            repo="org/repo",
        )

        self.report = StatsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            prs=[self.pr_open, self.pr_merged],
            issues=[self.issue_open],
        )

    def test_get_open_prs(self):
        open_prs = self.report.get_open_prs()
        self.assertEqual(len(open_prs), 1)
        self.assertEqual(open_prs[0].title, "Open PR")

    def test_get_merged_prs(self):
        merged_prs = self.report.get_merged_prs()
        self.assertEqual(len(merged_prs), 1)
        self.assertEqual(merged_prs[0].title, "Merged PR")

    def test_get_open_issues(self):
        open_issues = self.report.get_open_issues()
        self.assertEqual(len(open_issues), 1)
        self.assertEqual(open_issues[0].title, "Open Issue")

    def test_get_authors(self):
        authors = self.report.get_authors()
        self.assertEqual(len(authors), 2)
        author_names = {author.name for author in authors}
        self.assertEqual(author_names, {"User One", "User Two"})

    def test_count_methods(self):
        self.assertEqual(self.report.count_open_prs(), 1)
        self.assertEqual(self.report.count_merged_prs(), 1)
        self.assertEqual(self.report.count_open_issues(), 1)


class ReportFormatterTests(TestCase):
    def setUp(self):
        self.author = Author(github_username="testuser", name="Test User")
        self.pr = PR(
            title="Test PR",
            number=123,
            url="https://github.com/org/repo/pull/123",
            author=self.author,
            created_at=date(2024, 1, 15),
            merged_at=date(2024, 1, 20),
            state="closed",
            repo="org/repo",
        )
        self.issue = Issue(
            title="Test Issue",
            number=456,
            url="https://github.com/org/repo/issues/456",
            author=self.author,
            created_at=date(2024, 1, 10),
            state="open",
            repo="org/repo",
        )
        self.report = StatsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            prs=[self.pr],
            issues=[self.issue],
        )

    def test_format_html_with_data(self):
        html = ReportFormatter.format_html(self.report)

        self.assertIn('<div class="stats-summary">', html)
        self.assertIn('<div class="merged-prs">', html)
        self.assertIn('<div class="open-issues">', html)
        self.assertIn("Test PR", html)
        self.assertIn("Test Issue", html)
        self.assertIn("Test User", html)
        self.assertIn("org/repo", html)
        self.assertIn("<strong>1</strong>", html)

    def test_format_html_empty_report(self):
        empty_report = StatsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            prs=[],
            issues=[],
        )

        html = ReportFormatter.format_html(empty_report)
        self.assertIn("No GitHub activity found", html)
        self.assertIn("Try selecting a different date range", html)
