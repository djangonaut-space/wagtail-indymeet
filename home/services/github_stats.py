"""
GitHub Stats Collection Service for Djangonaut Space.

This module provides functionality to collect GitHub statistics (PRs and Issues)
for Djangonauts participating in mentoring sessions.

Issue #615: Collect djangonaut stats from admin
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import cached_property

from django.conf import settings
from github import Github

logger = logging.getLogger(__name__)

# GitHub item state constants
STATE_OPEN = "open"
STATE_CLOSED = "closed"


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
    state: str
    repo: str

    @property
    def is_open(self) -> bool:
        """Check if PR is open."""
        return self.state == STATE_OPEN

    @property
    def is_merged(self) -> bool:
        """Check if PR was merged."""
        return self.merged_at is not None

    @property
    def is_closed(self) -> bool:
        """Check if PR was closed without merging."""
        return self.state == STATE_CLOSED and self.merged_at is None


@dataclass
class Issue:
    """Represents a GitHub Issue."""

    title: str
    number: int
    url: str
    author: Author
    created_at: date
    state: str
    repo: str

    @property
    def is_open(self) -> bool:
        """Check if issue is open."""
        return self.state == STATE_OPEN


@dataclass
class StatsReport:
    """Aggregates GitHub statistics for a date range."""

    start_date: date
    end_date: date
    prs: list[PR] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @cached_property
    def open_prs(self) -> list[PR]:
        """Get all open PRs."""
        return [pr for pr in self.prs if pr.is_open]

    @cached_property
    def merged_prs(self) -> list[PR]:
        """Get all merged PRs."""
        return [pr for pr in self.prs if pr.is_merged]

    @cached_property
    def closed_prs(self) -> list[PR]:
        """Get all closed PRs (closed without merging)."""
        return [pr for pr in self.prs if pr.is_closed]

    @cached_property
    def open_issues(self) -> list[Issue]:
        """Get all open issues."""
        return [issue for issue in self.issues if issue.is_open]

    @cached_property
    def authors(self) -> set[Author]:
        """Get unique authors from PRs and issues."""
        return {pr.author for pr in self.prs} | {issue.author for issue in self.issues}

    def count_open_prs(self) -> int:
        """Count open PRs."""
        return len(self.open_prs)

    def count_merged_prs(self) -> int:
        """Count merged PRs."""
        return len(self.merged_prs)

    def count_closed_prs(self) -> int:
        """Count closed PRs (closed without merging)."""
        return len(self.closed_prs)

    def count_open_issues(self) -> int:
        """Count open issues."""
        return len(self.open_issues)


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

    def _parse_date(self, dt: datetime) -> date | None:
        """Convert datetime to date."""
        if not dt:
            return None
        if isinstance(dt, date) and not isinstance(dt, datetime):
            return dt
        return dt.date()

    def _build_author(self, github_username: str) -> Author:
        """
        Build an author from the GitHub login.

        Search results do not include the user's profile name. Using the login
        avoids an extra GitHub API request for every result.
        """
        return Author(github_username=github_username, name=github_username)

    def _build_search_queries(
        self,
        *,
        scope_terms: list[str],
        usernames: list[str],
        item_type: str,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """Build scoped GitHub search queries for each user."""
        scope_clause = " ".join(dict.fromkeys(scope_terms))
        unique_usernames = list(dict.fromkeys(usernames))

        return [
            " ".join(
                part
                for part in (
                    scope_clause,
                    f"author:{username}",
                    f"type:{item_type}",
                    f"created:{start_date}..{end_date}",
                )
                if part
            )
            for username in unique_usernames
        ]

    def _get_repo_full_name(self, item) -> str:
        """Get the repository full name without forcing a repository lookup."""
        repository_url = getattr(item, "repository_url", None)
        if isinstance(repository_url, str) and repository_url:
            if "/repos/" in repository_url:
                return repository_url.rstrip("/").split("/repos/", 1)[1]
            return "/".join(repository_url.rstrip("/").split("/")[-2:])

        return item.repository.full_name

    def _pr_from_search_result(self, item, repo_full_name: str) -> PR:
        """Convert a GitHub search result into a PR object."""
        pull_request = item.pull_request
        merged_at = (
            self._parse_date(pull_request.merged_at)
            if pull_request and pull_request.merged_at
            else None
        )

        return PR(
            title=item.title,
            number=item.number,
            url=item.html_url,
            author=self._build_author(item.user.login),
            created_at=self._parse_date(item.created_at),
            merged_at=merged_at,
            state=STATE_OPEN if item.state == STATE_OPEN else STATE_CLOSED,
            repo=repo_full_name,
        )

    def _issue_from_search_result(self, item, repo_full_name: str) -> Issue:
        """Convert a GitHub search result into an Issue object."""
        return Issue(
            title=item.title,
            number=item.number,
            url=item.html_url,
            author=self._build_author(item.user.login),
            created_at=self._parse_date(item.created_at),
            state=STATE_OPEN if item.state == STATE_OPEN else STATE_CLOSED,
            repo=repo_full_name,
        )

    def _build_allowed_repos_and_scope_terms(
        self, repos: list[dict]
    ) -> tuple[set[str], list[str]]:
        """Build allowed repos for filtering and search scope terms for querying."""
        allowed_repos = set()
        scope_terms = []

        for repo_config in repos:
            owner = repo_config["owner"]
            configured_repos = repo_config["repos"]

            if configured_repos == ["*"]:
                target_repos = self._get_repos_from_config(owner, configured_repos)
                for repo_name in target_repos:
                    allowed_repos.add(f"{owner}/{repo_name}".lower())
                scope_terms.append(f"org:{owner}")
                continue

            for repo_name in configured_repos:
                allowed_repos.add(f"{owner}/{repo_name}".lower())
                scope_terms.append(f"repo:{owner}/{repo_name}")

        return allowed_repos, list(dict.fromkeys(scope_terms))

    def collect_prs_for_repo(
        self,
        owner: str,
        repo_name: str,
        usernames: list[str],
        start_date: date,
        end_date: date,
    ) -> list[PR]:
        """
        Collect PRs from a repository using GitHub Search API.

        Args:
            owner: Repository owner (org or user)
            repo_name: Repository name
            usernames: List of GitHub usernames to filter by
            start_date: Start date for filtering
            end_date: End date for filtering

        Returns:
            List of PR objects
        """
        repo_full_name = f"{owner}/{repo_name}"
        queries = self._build_search_queries(
            scope_terms=[f"repo:{repo_full_name}"],
            usernames=usernames,
            item_type="pr",
            start_date=start_date,
            end_date=end_date,
        )
        prs = []

        for query in queries:
            logger.debug("Searching: %s", query)
            results = self.github.search_issues(query)

            for item in results:
                pr = self._pr_from_search_result(item, repo_full_name)
                prs.append(pr)
                logger.debug(
                    "Found PR #%d by %s (merged: %s)",
                    item.number,
                    item.user.login,
                    pr.merged_at is not None,
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
        repo_full_name = f"{owner}/{repo_name}"
        queries = self._build_search_queries(
            scope_terms=[f"repo:{repo_full_name}"],
            usernames=usernames,
            item_type="issue",
            start_date=start_date,
            end_date=end_date,
        )
        issues_list = []

        for query in queries:
            logger.debug("Searching: %s", query)
            results = self.github.search_issues(query)

            for item in results:
                issue_obj = self._issue_from_search_result(item, repo_full_name)
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

        allowed_repos, scope_terms = self._build_allowed_repos_and_scope_terms(repos)

        logger.info("Monitoring %d repositories", len(allowed_repos))
        if not scope_terms:
            logger.info("No repository scopes were resolved for stats collection")
            return report

        pr_queries = self._build_search_queries(
            scope_terms=scope_terms,
            usernames=usernames,
            item_type="pr",
            start_date=start_date,
            end_date=end_date,
        )
        issue_queries = self._build_search_queries(
            scope_terms=scope_terms,
            usernames=usernames,
            item_type="issue",
            start_date=start_date,
            end_date=end_date,
        )
        logger.info(
            "Running %d PR searches and %d issue searches",
            len(pr_queries),
            len(issue_queries),
        )

        for pr_query in pr_queries:
            logger.debug("Searching PRs: %s", pr_query)

            pr_results = self.github.search_issues(pr_query)
            for item in pr_results:
                repo_full_name = self._get_repo_full_name(item)
                if repo_full_name.lower() not in allowed_repos:
                    continue

                pr = self._pr_from_search_result(item, repo_full_name)
                report.prs.append(pr)
                logger.debug(
                    "Found PR #%d in %s (merged: %s)",
                    item.number,
                    repo_full_name.lower(),
                    pr.merged_at is not None,
                )

        for issue_query in issue_queries:
            logger.debug("Searching issues: %s", issue_query)

            issue_results = self.github.search_issues(issue_query)
            for item in issue_results:
                repo_full_name = self._get_repo_full_name(item)
                if repo_full_name.lower() not in allowed_repos:
                    continue

                issue = self._issue_from_search_result(item, repo_full_name)
                report.issues.append(issue)
                logger.debug(
                    "Found issue #%d in %s", item.number, repo_full_name.lower()
                )

        logger.info(
            "Collection complete: %d PRs, %d issues",
            len(report.prs),
            len(report.issues),
        )
        return report
