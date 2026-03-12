"""
GitHub Stats Collection Service for Djangonaut Space.

This module provides functionality to collect GitHub statistics (PRs and Issues)
for Djangonauts participating in mentoring sessions.

Issue #615: Collect djangonaut stats from admin
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime

from django.conf import settings
from github import Github, GithubException

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
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

    @property
    def is_closed(self) -> bool:
        """Check if PR was closed without merging."""
        return self.state == "closed" and self.merged_at is None


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

    def get_closed_prs(self) -> list[PR]:
        """Get all closed PRs (closed without merging)."""
        return [pr for pr in self.prs if pr.is_closed]

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

    def count_closed_prs(self) -> int:
        """Count closed PRs (closed without merging)."""
        return len(self.get_closed_prs())

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
        Collect PRs from a repository using GitHub Search API.

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

        # Use Search API for each username - much faster than iterating all PRs
        for username in usernames:
            query = (
                f"repo:{owner}/{repo_name} "
                f"type:pr "
                f"author:{username} "
                f"created:{start_date}..{end_date}"
            )
            logger.debug("Searching: %s", query)

            results = self.github.search_issues(query)

            for item in results:
                author = Author(
                    github_username=item.user.login,
                    name=item.user.name or item.user.login,
                )

                # Fetch the actual PR to get merged_at
                pull_request = item.as_pull_request()
                merged_at = (
                    self._parse_date(pull_request.merged_at)
                    if pull_request.merged_at
                    else None
                )

                pr = PR(
                    title=item.title,
                    number=item.number,
                    url=item.html_url,
                    author=author,
                    created_at=self._parse_date(item.created_at),
                    merged_at=merged_at,
                    state="open" if item.state == "open" else "closed",
                    repo=f"{owner}/{repo_name}",
                )
                prs.append(pr)
                logger.debug(
                    "Found PR #%d by %s (merged: %s)",
                    item.number,
                    item.user.login,
                    merged_at is not None,
                )

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
        Collect Issues from a repository using GitHub Search API.

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

        # Use Search API for each username - much faster than iterating all issues
        for username in usernames:
            query = (
                f"repo:{owner}/{repo_name} "
                f"type:issue "
                f"author:{username} "
                f"created:{start_date}..{end_date}"
            )
            logger.debug("Searching: %s", query)

            results = self.github.search_issues(query)

            for item in results:
                author = Author(
                    github_username=item.user.login,
                    name=item.user.name or item.user.login,
                )

                issue_obj = Issue(
                    title=item.title,
                    number=item.number,
                    url=item.html_url,
                    author=author,
                    created_at=self._parse_date(item.created_at),
                    state="open" if item.state == "open" else "closed",
                    repo=f"{owner}/{repo_name}",
                )
                issues_list.append(issue_obj)
                logger.debug("Found issue #%d by %s", item.number, item.user.login)

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
            logger.info("Resolving wildcard repositories for %s", owner)
            org = self.github.get_organization(owner)
            # Fetch only sources, not forks, to avoid noise
            # and limit to public repos usually, though 'all' is default
            repo_names = [repo.name for repo in org.get_repos(type="sources")]
            logger.info("Found %d repos for %s", len(repo_names), owner)
            return repo_names
        return repos

    def collect_all_stats(
        self, repos: list[dict], usernames: list[str], start_date: date, end_date: date
    ) -> StatsReport:
        """
        Collect all stats across multiple repositories using efficient search.

        Uses GitHub Search API to find all PRs/issues by user in date range,
        then filters to configured repositories.

        Args:
            repos: List of repo dicts with 'owner' and 'repos' keys
            usernames: List of GitHub usernames to track
            start_date: Start date for filtering
            end_date: End date for filtering

        Returns:
            StatsReport with all collected data
        """
        report = StatsReport(start_date=start_date, end_date=end_date)

        logger.info("Starting stats collection for %d users", len(usernames))
        logger.info("Date range: %s to %s", start_date, end_date)
        logger.debug("Usernames: %s", usernames)

        # Build set of allowed repos for filtering
        allowed_repos = set()
        for repo_config in repos:
            owner = repo_config["owner"]
            configured_repos = repo_config["repos"]

            if configured_repos == ["*"]:
                # For wildcards, we'll filter by org later
                target_repos = self._get_repos_from_config(owner, configured_repos)
                for repo_name in target_repos:
                    allowed_repos.add(f"{owner}/{repo_name}".lower())
            else:
                for repo_name in configured_repos:
                    allowed_repos.add(f"{owner}/{repo_name}".lower())

        logger.info("Monitoring %d repositories", len(allowed_repos))

        # Search for each user's PRs and issues (only 2 API calls per user!)
        for username in usernames:
            # Search for PRs
            pr_query = f"type:pr author:{username} created:{start_date}..{end_date}"
            logger.debug("Searching PRs: %s", pr_query)

            pr_results = self.github.search_issues(pr_query)
            for item in pr_results:
                repo_full_name = item.repository.full_name.lower()
                if repo_full_name in allowed_repos:
                    author = Author(
                        github_username=item.user.login,
                        name=item.user.name or item.user.login,
                    )
                    # Fetch the actual PR to get merged_at
                    pull_request = item.as_pull_request()
                    merged_at = (
                        self._parse_date(pull_request.merged_at)
                        if pull_request.merged_at
                        else None
                    )
                    pr = PR(
                        title=item.title,
                        number=item.number,
                        url=item.html_url,
                        author=author,
                        created_at=self._parse_date(item.created_at),
                        merged_at=merged_at,
                        state="open" if item.state == "open" else "closed",
                        repo=item.repository.full_name,
                    )
                    report.prs.append(pr)
                    logger.debug(
                        "Found PR #%d in %s (merged: %s)",
                        item.number,
                        repo_full_name,
                        merged_at is not None,
                    )

            # Search for issues
            issue_query = (
                f"type:issue author:{username} created:{start_date}..{end_date}"
            )
            logger.debug("Searching issues: %s", issue_query)

            issue_results = self.github.search_issues(issue_query)
            for item in issue_results:
                repo_full_name = item.repository.full_name.lower()
                if repo_full_name in allowed_repos:
                    author = Author(
                        github_username=item.user.login,
                        name=item.user.name or item.user.login,
                    )
                    issue = Issue(
                        title=item.title,
                        number=item.number,
                        url=item.html_url,
                        author=author,
                        created_at=self._parse_date(item.created_at),
                        state="open" if item.state == "open" else "closed",
                        repo=item.repository.full_name,
                    )
                    report.issues.append(issue)
                    logger.debug("Found issue #%d in %s", item.number, repo_full_name)

        logger.info(
            "Collection complete: %d PRs, %d issues",
            len(report.prs),
            len(report.issues),
        )
        return report
