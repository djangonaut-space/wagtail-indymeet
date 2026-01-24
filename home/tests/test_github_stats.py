from datetime import date
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from accounts.factories import ProfileFactory, UserFactory
from home.factories import SessionFactory, SessionMembershipFactory
from home.models.session import SessionMembership
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

    def test_parse_date(self):
        """Test _parse_date helper method."""
        from datetime import datetime

        collector = GitHubStatsCollector(self.mock_token)

        # Test datetime conversion
        dt = datetime(2024, 1, 15, 12, 0, 0)
        self.assertEqual(collector._parse_date(dt), date(2024, 1, 15))

        # Test date pass-through
        d = date(2024, 1, 15)
        self.assertEqual(collector._parse_date(d), d)

        # Test None
        self.assertIsNone(collector._parse_date(None))


class DataClassesTests(TestCase):
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

        self.report = StatsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            prs=[self.pr_open, self.pr_merged, self.pr_closed],
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

    def test_get_closed_prs(self):
        closed_prs = self.report.get_closed_prs()
        self.assertEqual(len(closed_prs), 1)
        self.assertEqual(closed_prs[0].title, "Closed PR")

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
        self.assertEqual(self.report.count_closed_prs(), 1)
        self.assertEqual(self.report.count_open_issues(), 1)

    def test_pr_is_closed(self):
        """Test that is_closed property correctly identifies closed PRs."""
        self.assertTrue(self.pr_closed.is_closed)
        self.assertFalse(self.pr_merged.is_closed)  # merged PR should not be closed
        self.assertFalse(self.pr_open.is_closed)  # open PR should not be closed


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
        self.pr_closed = PR(
            title="Closed PR",
            number=124,
            url="https://github.com/org/repo/pull/124",
            author=self.author,
            created_at=date(2024, 1, 12),
            merged_at=None,
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
            prs=[self.pr, self.pr_closed],
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

    def test_format_html_with_closed_prs(self):
        """Test that closed PRs section appears in HTML output."""
        html = ReportFormatter.format_html(self.report)

        # Check for closed PRs section
        self.assertIn('<div class="closed-prs">', html)
        self.assertIn("🚧 Closed Pull Requests", html)
        self.assertIn("Closed PR", html)

        # Check for merged PRs section
        self.assertIn('<div class="merged-prs">', html)
        self.assertIn("🎉 Merged Pull Requests", html)
        self.assertIn("Test PR", html)

        # Verify counts in stats summary
        self.assertIn("Closed PRs", html)
        self.assertIn("Merged PRs", html)


class CollectStatsViewIntegrationTests(TestCase):
    """
    Integration tests for the collect_stats_view admin interface.

    These tests verify the complete flow from view to display,
    mocking GitHub API calls to test data handling and presentation.
    """

    def setUp(self):
        """Set up test data for integration tests."""
        # Create staff user for admin access
        self.staff_user = UserFactory.create(is_staff=True, is_superuser=True)
        self.client = Client()
        self.client.force_login(self.staff_user)

        # Create session with Djangonauts
        self.session = SessionFactory.create(
            title="Test Session",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
        )

        # Create Djangonauts with GitHub usernames
        self.djangonaut1 = UserFactory.create()
        # Get profile from DB and update
        from accounts.models import UserProfile

        profile1 = UserProfile.objects.get(user=self.djangonaut1)
        profile1.github_username = "djangonaut1"
        profile1.save()
        # Reload user to get fresh profile
        self.djangonaut1 = self.djangonaut1.__class__.objects.get(
            pk=self.djangonaut1.pk
        )
        SessionMembershipFactory.create(
            session=self.session,
            user=self.djangonaut1,
            role=SessionMembership.DJANGONAUT,
        )

        self.djangonaut2 = UserFactory.create()
        # Get profile from DB and update
        profile2 = UserProfile.objects.get(user=self.djangonaut2)
        profile2.github_username = "djangonaut2"
        profile2.save()
        # Reload user to get fresh profile
        self.djangonaut2 = self.djangonaut2.__class__.objects.get(
            pk=self.djangonaut2.pk
        )
        SessionMembershipFactory.create(
            session=self.session,
            user=self.djangonaut2,
            role=SessionMembership.DJANGONAUT,
        )

        # URL for collect stats view
        self.url = reverse(
            "admin:session_collect_stats", kwargs={"session_id": self.session.id}
        )

    def _create_mock_github_item(
        self,
        title,
        number,
        state,
        merged_at=None,
        item_type="pr",
        username="djangonaut1",
    ):
        """Helper to create mock GitHub API response items."""
        mock_item = Mock()
        mock_item.title = title
        mock_item.number = number
        mock_item.html_url = (
            f"https://github.com/test-org/test-repo/{item_type}/{number}"
        )
        mock_item.state = state
        mock_item.created_at = date(2024, 1, 15)

        # Mock user
        mock_user = Mock()
        mock_user.login = username
        mock_user.name = username.title()
        mock_item.user = mock_user

        # Mock repository
        mock_repo = Mock()
        mock_repo.full_name = "test-org/test-repo"
        mock_item.repository = mock_repo

        return mock_item

    @override_settings(
        GITHUB_TOKEN="test_token",
        DJANGONAUT_MONITORED_REPOS=[{"owner": "test-org", "repos": ["test-repo"]}],
    )
    @patch("home.views.sessions.GitHubStatsCollector")
    def test_collect_stats_view_with_mixed_pr_states(self, mock_collector_class):
        """
        Integration test: Verify view correctly displays mixed PR states.

        Tests that the admin view properly handles and displays:
        - Open PRs
        - Merged PRs (closed with merge date)
        - Closed PRs (closed without merge)
        """
        # Create mock collector instance
        mock_collector = Mock()
        mock_collector_class.return_value = mock_collector

        # Create mock GitHub items with different states
        mock_open_pr = self._create_mock_github_item(
            "Open PR", 1, "open", merged_at=None
        )
        mock_merged_pr = self._create_mock_github_item(
            "Merged PR", 2, "closed", merged_at=date(2024, 1, 20)
        )
        mock_closed_pr = self._create_mock_github_item(
            "Closed PR", 3, "closed", merged_at=None
        )
        mock_issue = self._create_mock_github_item(
            "Test Issue", 10, "open", item_type="issues"
        )

        # Mock the collect_all_stats method to return our test data
        mock_report = StatsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            prs=[
                PR(
                    title="Open PR",
                    number=1,
                    url="https://github.com/test-org/test-repo/pull/1",
                    author=Author(github_username="djangonaut1", name="Djangonaut1"),
                    created_at=date(2024, 1, 15),
                    merged_at=None,
                    state="open",
                    repo="test-org/test-repo",
                ),
                PR(
                    title="Merged PR",
                    number=2,
                    url="https://github.com/test-org/test-repo/pull/2",
                    author=Author(github_username="djangonaut2", name="Djangonaut2"),
                    created_at=date(2024, 1, 10),
                    merged_at=date(2024, 1, 20),
                    state="closed",
                    repo="test-org/test-repo",
                ),
                PR(
                    title="Closed PR",
                    number=3,
                    url="https://github.com/test-org/test-repo/pull/3",
                    author=Author(github_username="djangonaut1", name="Djangonaut1"),
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
                    author=Author(github_username="djangonaut1", name="Djangonaut1"),
                    created_at=date(2024, 1, 18),
                    state="open",
                    repo="test-org/test-repo",
                )
            ],
        )
        mock_collector.collect_all_stats.return_value = mock_report

        # Make request to collect stats
        response = self.client.get(self.url, {"collect": "true"})

        # Debug output
        if response.status_code == 302:
            print(f"\nDEBUG: Got redirect to {response.url}")
            messages_list = list(get_messages(response.wsgi_request))
            if messages_list:
                print("Messages:")
                for msg in messages_list:
                    print(f"  - {msg}")

        # Verify response
        self.assertEqual(response.status_code, 200)

        # Verify collector was called with correct parameters
        mock_collector.collect_all_stats.assert_called_once()
        call_kwargs = mock_collector.collect_all_stats.call_args
        self.assertEqual(call_kwargs[1]["start_date"], date(2024, 1, 1))
        self.assertEqual(call_kwargs[1]["end_date"], date(2024, 1, 31))
        self.assertIn("djangonaut1", call_kwargs[1]["usernames"])
        self.assertIn("djangonaut2", call_kwargs[1]["usernames"])

        # Verify success message includes all PR types
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        success_message = str(messages[0])
        self.assertIn("1 open PRs", success_message)
        self.assertIn("1 merged PRs", success_message)
        self.assertIn("1 closed PRs", success_message)
        self.assertIn("1 issues", success_message)

        # Verify HTML content includes all sections
        content = response.content.decode()

        # Check for merged PRs section
        self.assertIn("🎉 Merged Pull Requests", content)
        self.assertIn("Merged PR", content)

        # Check for closed PRs section
        self.assertIn("🚧 Closed Pull Requests", content)
        self.assertIn("Closed PR", content)

        # Check for open PRs section
        self.assertIn("✨ Open Pull Requests", content)
        self.assertIn("Open PR", content)

        # Check for issues section
        self.assertIn("✏️ Issues", content)
        self.assertIn("Test Issue", content)

        # Verify stats summary
        self.assertIn("Open PRs", content)
        self.assertIn("Merged PRs", content)
        self.assertIn("Closed PRs", content)

    @override_settings(
        GITHUB_TOKEN="test_token",
        DJANGONAUT_MONITORED_REPOS=[{"owner": "test-org", "repos": ["test-repo"]}],
    )
    @patch("home.views.sessions.GitHubStatsCollector")
    def test_collect_stats_view_only_closed_prs(self, mock_collector_class):
        """
        Integration test: Verify view handles sessions with only closed PRs.

        Edge case test to ensure closed PRs are properly displayed
        when there are no merged or open PRs.
        """
        mock_collector = Mock()
        mock_collector_class.return_value = mock_collector

        # Create report with only closed PRs
        mock_report = StatsReport(
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            prs=[
                PR(
                    title="Closed PR 1",
                    number=1,
                    url="https://github.com/test-org/test-repo/pull/1",
                    author=Author(github_username="djangonaut1", name="Djangonaut1"),
                    created_at=date(2024, 1, 15),
                    merged_at=None,
                    state="closed",
                    repo="test-org/test-repo",
                ),
                PR(
                    title="Closed PR 2",
                    number=2,
                    url="https://github.com/test-org/test-repo/pull/2",
                    author=Author(github_username="djangonaut2", name="Djangonaut2"),
                    created_at=date(2024, 1, 18),
                    merged_at=None,
                    state="closed",
                    repo="test-org/test-repo",
                ),
            ],
            issues=[],
        )
        mock_collector.collect_all_stats.return_value = mock_report

        # Make request
        response = self.client.get(self.url, {"collect": "true"})

        # Verify response
        self.assertEqual(response.status_code, 200)

        # Verify success message
        messages = list(get_messages(response.wsgi_request))
        success_message = str(messages[0])
        self.assertIn("0 open PRs", success_message)
        self.assertIn("0 merged PRs", success_message)
        self.assertIn("2 closed PRs", success_message)

        # Verify HTML content
        content = response.content.decode()
        self.assertIn("🚧 Closed Pull Requests", content)
        self.assertIn("Closed PR 1", content)
        self.assertIn("Closed PR 2", content)

        # Should not have merged or open PR sections
        self.assertNotIn("🎉 Merged Pull Requests", content)
        self.assertNotIn("✨ Open Pull Requests", content)

    @override_settings(
        GITHUB_TOKEN="test_token",
        DJANGONAUT_MONITORED_REPOS=[{"owner": "test-org", "repos": ["test-repo"]}],
    )
    @patch("home.views.sessions.GitHubStatsCollector")
    def test_collect_stats_view_form_display(self, mock_collector_class):
        """
        Integration test: Verify stats collection form displays correctly.

        Tests the initial GET request without 'collect' parameter
        shows the date selection form.
        """
        # Make GET request without 'collect' parameter
        response = self.client.get(self.url)

        # Verify response
        self.assertEqual(response.status_code, 200)

        # Verify form elements are present
        content = response.content.decode()
        self.assertIn("start_date", content)
        self.assertIn("end_date", content)
        self.assertIn(self.session.title, content)

        # Verify collector was not called yet
        mock_collector_class.assert_not_called()

    @override_settings(GITHUB_TOKEN="test_token", DJANGONAUT_MONITORED_REPOS=[])
    def test_collect_stats_view_no_repos_configured(self):
        """
        Integration test: Verify error handling when no repos configured.

        Tests that appropriate error message is shown when
        DJANGONAUT_MONITORED_REPOS is not set.
        """
        # Make request without repos configured
        response = self.client.get(self.url, {"collect": "true"})

        # Should redirect to session changelist
        self.assertEqual(response.status_code, 302)

        # Verify error message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        error_message = str(messages[0])
        self.assertIn("No repositories configured", error_message)

    @override_settings(
        GITHUB_TOKEN="test_token",
        DJANGONAUT_MONITORED_REPOS=[{"owner": "test-org", "repos": ["test-repo"]}],
    )
    def test_collect_stats_view_no_github_usernames(self):
        """
        Integration test: Verify handling when no Djangonauts have GitHub usernames.

        Tests that appropriate warning is shown when Djangonauts
        don't have GitHub usernames configured.
        """
        # Remove GitHub usernames from profiles
        self.djangonaut1.profile.github_username = ""
        self.djangonaut1.profile.save()
        self.djangonaut2.profile.github_username = ""
        self.djangonaut2.profile.save()

        # Make request
        response = self.client.get(self.url, {"collect": "true"})

        # Should redirect to session changelist
        self.assertEqual(response.status_code, 302)

        # Verify warning message
        messages = list(get_messages(response.wsgi_request))
        self.assertEqual(len(messages), 1)
        warning_message = str(messages[0])
        self.assertIn("No Djangonauts", warning_message)
        self.assertIn("GitHub usernames", warning_message)

    @override_settings(
        GITHUB_TOKEN="test_token",
        DJANGONAUT_MONITORED_REPOS=[{"owner": "test-org", "repos": ["test-repo"]}],
    )
    @patch("home.views.sessions.GitHubStatsCollector")
    def test_collect_stats_view_custom_date_range(self, mock_collector_class):
        """
        Integration test: Verify custom date range handling.

        Tests that POST request with custom dates properly
        passes those dates to the collector.
        """
        mock_collector = Mock()
        mock_collector_class.return_value = mock_collector

        # Create empty report
        mock_report = StatsReport(
            start_date=date(2024, 2, 1),
            end_date=date(2024, 2, 15),
            prs=[],
            issues=[],
        )
        mock_collector.collect_all_stats.return_value = mock_report

        # Make POST request with custom dates
        response = self.client.post(
            self.url,
            {
                "start_date": "2024-02-01",
                "end_date": "2024-02-15",
            },
        )

        # Verify response
        self.assertEqual(response.status_code, 200)

        # Verify collector was called with custom dates
        mock_collector.collect_all_stats.assert_called_once()
        call_kwargs = mock_collector.collect_all_stats.call_args
        self.assertEqual(call_kwargs[1]["start_date"], date(2024, 2, 1))
        self.assertEqual(call_kwargs[1]["end_date"], date(2024, 2, 15))
