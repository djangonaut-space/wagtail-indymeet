"""
GitHub Stats Collection Service for Djangonaut Space.

This module provides functionality to collect GitHub statistics (PRs and Issues)
for Djangonauts participating in mentoring sessions.

Issue #615: Collect djangonaut stats from admin
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
import logging

from github import Github, GithubException
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class Author:
    """Represents a GitHub author."""

    github_username: str
    name: str


@dataclass
class PR:
    """Represents a GitHub Pull Request."""

    title: str
    number: int
    url: str
    author: Author
    created_at: date
    merged_at: date | None
    state: str  # 'open' or 'closed'
    repo: str

    @property
    def is_open(self) -> bool:
        """Check if PR is open."""
        return self.state == "open"

    @property
    def is_merged(self) -> bool:
        """Check if PR was merged."""
        return self.merged_at is not None


@dataclass
class Issue:
    """Represents a GitHub Issue."""

    title: str
    number: int
    url: str
    author: Author
    created_at: date
    state: str  # 'open' or 'closed'
    repo: str

    @property
    def is_open(self) -> bool:
        """Check if issue is open."""
        return self.state == "open"


@dataclass
class StatsReport:
    """Aggregates GitHub statistics for a date range."""

    start_date: date
    end_date: date
    prs: list[PR] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    def get_open_prs(self) -> list[PR]:
        """Get all open PRs."""
        return [pr for pr in self.prs if pr.is_open]

    def get_merged_prs(self) -> list[PR]:
        """Get all merged PRs."""
        return [pr for pr in self.prs if pr.is_merged]

    def get_open_issues(self) -> list[Issue]:
        """Get all open issues."""
        return [issue for issue in self.issues if issue.is_open]

    def get_authors(self) -> set[Author]:
        """Get unique authors from PRs and issues."""
        authors = set()
        for pr in self.prs:
            authors.add(pr.author)
        for issue in self.issues:
            authors.add(issue.author)
        return authors

    def count_open_prs(self) -> int:
        """Count open PRs."""
        return len(self.get_open_prs())

    def count_merged_prs(self) -> int:
        """Count merged PRs."""
        return len(self.get_merged_prs())

    def count_open_issues(self) -> int:
        """Count open issues."""
        return len(self.get_open_issues())


class GitHubStatsCollector:
    """
    Collects GitHub statistics for Djangonauts.

    Uses PyGithub to fetch PRs and Issues from configured repositories
    for specified users within a date range.
    """

    def __init__(self, github_token: str | None = None):
        """
        Initialize the collector with GitHub token.

        Args:
            github_token: GitHub personal access token. If None, uses settings.GITHUB_TOKEN
        """
        token = github_token or settings.GITHUB_TOKEN
        if not token:
            raise ValueError("GitHub token is required. Set GITHUB_TOKEN in settings.")

        self.github = Github(token)
        logger.info("GitHubStatsCollector initialized")

    def _parse_date(self, dt: datetime) -> date:
        """Convert datetime to date."""
        if isinstance(dt, date) and not isinstance(dt, datetime):
            return dt
        return dt.date() if dt else None

    def collect_prs_for_repo(
        self,
        owner: str,
        repo_name: str,
        usernames: list[str],
        start_date: date,
        end_date: date,
        state: str = "all",
    ) -> list[PR]:
        """
        Collect PRs from a repository.

        Args:
            owner: Repository owner (org or user)
            repo_name: Repository name
            usernames: List of GitHub usernames to filter by
            start_date: Start date for filtering
            end_date: End date for filtering
            state: PR state ('open', 'closed', or 'all')

        Returns:
            List of PR objects
        """
        prs = []

        try:
            repo = self.github.get_repo(f"{owner}/{repo_name}")
            logger.info(f"Fetching PRs from {owner}/{repo_name}")

            # Get PRs created in date range
            pulls = repo.get_pulls(state=state, sort="created", direction="desc")

            for pull in pulls:
                # Check if PR was created in our date range
                pr_created = self._parse_date(pull.created_at)

                # Since results are sorted by created desc, if we see a PR created
                # before start_date, we can stop processing.
                if pr_created < start_date:
                    break

                if pr_created > end_date:
                    continue

                # Check if author is in our list
                # (optimization: convert to set if not already, though caller handles it)
                if pull.user and pull.user.login.lower() in usernames:
                    author = Author(
                        github_username=pull.user.login,
                        name=pull.user.name or pull.user.login,
                    )

                    pr = PR(
                        title=pull.title,
                        number=pull.number,
                        url=pull.html_url,
                        author=author,
                        created_at=pr_created,
                        merged_at=self._parse_date(pull.merged_at),
                        state="open" if pull.state == "open" else "closed",
                        repo=f"{owner}/{repo_name}",
                    )
                    prs.append(pr)
                    logger.debug(f"Found PR #{pull.number} by {pull.user.login}")

        except GithubException as e:
            logger.error(f"GitHub API error for {owner}/{repo_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error collecting PRs from {owner}/{repo_name}: {e}")
            raise

        return prs

    def collect_issues_for_repo(
        self,
        owner: str,
        repo_name: str,
        usernames: list[str],
        start_date: date,
        end_date: date,
    ) -> list[Issue]:
        """
        Collect Issues from a repository.

        Args:
            owner: Repository owner (org or user)
            repo_name: Repository name
            usernames: List of GitHub usernames to filter by
            start_date: Start date for filtering
            end_date: End date for filtering

        Returns:
            List of Issue objects
        """
        issues_list = []

        try:
            repo = self.github.get_repo(f"{owner}/{repo_name}")
            logger.info(f"Fetching issues from {owner}/{repo_name}")

            # Get issues created in date range
            issues = repo.get_issues(state="all", sort="created", direction="desc")

            for issue in issues:
                # Skip pull requests (GitHub API returns PRs as issues)
                if issue.pull_request:
                    continue

                # Check if issue was created in our date range
                issue_created = self._parse_date(issue.created_at)

                # Since results are sorted by created desc, if we see an issue created
                # before start_date, we can stop processing.
                if issue_created < start_date:
                    break

                if issue_created > end_date:
                    continue

                # Check if author is in our list
                if issue.user and issue.user.login.lower() in usernames:
                    author = Author(
                        github_username=issue.user.login,
                        name=issue.user.name or issue.user.login,
                    )

                    issue_obj = Issue(
                        title=issue.title,
                        number=issue.number,
                        url=issue.html_url,
                        author=author,
                        created_at=issue_created,
                        state="open" if issue.state == "open" else "closed",
                        repo=f"{owner}/{repo_name}",
                    )
                    issues_list.append(issue_obj)
                    logger.debug(f"Found issue #{issue.number} by {issue.user.login}")

        except GithubException as e:
            logger.error(f"GitHub API error for {owner}/{repo_name}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error collecting issues from {owner}/{repo_name}: {e}")
            raise

        return issues_list

    def _get_repos_from_config(self, owner: str, repos: list[str]) -> list[str]:
        """
        Resolve list of repositories from configuration, handling wildcards.

        Args:
            owner: GitHub organization or user
            repos: List of repo names or ['*'] for all public repos

        Returns:
            List of repository names
        """
        if repos == ["*"]:
            try:
                logger.info(f"Resolving wildcard repositories for {owner}...")
                org = self.github.get_organization(owner)
                # Fetch only sources, not forks, to avoid noise
                # and limit to public repos usually, though 'all' is default
                return [repo.name for repo in org.get_repos(type="sources")]
            except GithubException as e:
                logger.error(f"Failed to resolve wildcard for {owner}: {e}")
                return []
        return repos

    def collect_all_stats(
        self, repos: list[dict], usernames: list[str], start_date: date, end_date: date
    ) -> StatsReport:
        """
        Collect all stats across multiple repositories.

        Args:
            repos: List of repo dicts with 'owner' and 'repos' keys
            usernames: List of GitHub usernames to track
            start_date: Start date for filtering
            end_date: End date for filtering

        Returns:
            StatsReport with all collected data
        """
        report = StatsReport(start_date=start_date, end_date=end_date)

        # Optimization: Pre-calculate lowercase usernames set for O(1) lookup
        username_set = {u.lower() for u in usernames}

        logger.info(
            f"Collecting stats for {len(usernames)} users from {start_date} to {end_date}"
        )

        for repo_config in repos:
            owner = repo_config["owner"]
            configured_repos = repo_config["repos"]

            # Resolve repositories (handles wildcards)
            target_repos = self._get_repos_from_config(owner, configured_repos)

            for repo_name in target_repos:
                try:
                    # Collect PRs
                    prs = self.collect_prs_for_repo(
                        owner, repo_name, list(username_set), start_date, end_date
                    )
                    report.prs.extend(prs)

                    # Collect Issues
                    issues = self.collect_issues_for_repo(
                        owner, repo_name, list(username_set), start_date, end_date
                    )
                    report.issues.extend(issues)

                    logger.info(
                        f"Collected {len(prs)} PRs and {len(issues)} "
                        f"issues from {owner}/{repo_name}"
                    )

                except Exception as e:
                    logger.error(f"Failed to collect from {owner}/{repo_name}: {e}")
                    # Continue with other repos
                    continue

        logger.info(f"Total: {len(report.prs)} PRs, {len(report.issues)} issues")
        return report
