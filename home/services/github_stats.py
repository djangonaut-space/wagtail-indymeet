"""GitHub stats collection service for Djangonaut Space sessions."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import cached_property

from django.conf import settings
from github import Github

logger = logging.getLogger(__name__)

STATE_OPEN = "open"
STATE_CLOSED = "closed"


@dataclass(frozen=True)
class Author:
    github_username: str
    name: str


@dataclass
class PR:
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
        return self.state == STATE_OPEN

    @property
    def is_merged(self) -> bool:
        return self.merged_at is not None

    @property
    def is_closed(self) -> bool:
        """Closed without merging."""
        return self.state == STATE_CLOSED and self.merged_at is None


@dataclass
class Issue:
    title: str
    number: int
    url: str
    author: Author
    created_at: date
    state: str
    repo: str

    @property
    def is_open(self) -> bool:
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
        return [pr for pr in self.prs if pr.is_open]

    @cached_property
    def merged_prs(self) -> list[PR]:
        return [pr for pr in self.prs if pr.is_merged]

    @cached_property
    def closed_prs(self) -> list[PR]:
        return [pr for pr in self.prs if pr.is_closed]

    @cached_property
    def open_issues(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.is_open]

    @cached_property
    def authors(self) -> set[Author]:
        return {pr.author for pr in self.prs} | {issue.author for issue in self.issues}

    def count_open_prs(self) -> int:
        return len(self.open_prs)

    def count_merged_prs(self) -> int:
        return len(self.merged_prs)

    def count_closed_prs(self) -> int:
        return len(self.closed_prs)

    def count_open_issues(self) -> int:
        return len(self.open_issues)


class GitHubStatsCollector:
    """Collects GitHub PR and Issue statistics using the GitHub Search API."""

    def __init__(self, github_token: str | None = None):
        token = github_token or settings.GITHUB_TOKEN
        if not token:
            raise ValueError("GitHub token is required. Set GITHUB_TOKEN in settings.")

        self.github = Github(token)
        logger.info("GitHubStatsCollector initialized")

    def _to_date(self, dt: datetime | date | None) -> date | None:
        """Convert a datetime to a date, passing through date and None unchanged."""
        if isinstance(dt, datetime):
            return dt.date()
        return dt

    def _build_search_queries(
        self,
        *,
        scope_terms: list[str],
        usernames: list[str],
        item_type: str,
        start_date: date,
        end_date: date,
    ) -> list[str]:
        """Build one GitHub search query per user, scoped to given repos/orgs."""
        scope_clause = " ".join(dict.fromkeys(scope_terms))
        unique_usernames = list(dict.fromkeys(usernames))

        return [
            f"{scope_clause} author:{username} type:{item_type} created:{start_date}..{end_date}"
            for username in unique_usernames
        ]

    def _get_repo_full_name(self, item) -> str:
        """Extract repository full name from a search result without an extra API call."""
        repository_url = getattr(item, "repository_url", None)
        if isinstance(repository_url, str) and repository_url:
            # GitHub API URLs follow the pattern https://api.github.com/repos/{owner}/{repo}
            if "/repos/" in repository_url:
                return repository_url.rstrip("/").split("/repos/", 1)[1]
            return "/".join(repository_url.rstrip("/").split("/")[-2:])

        return item.repository.full_name

    def _pr_from_search_result(self, item, repo_full_name: str) -> PR:
        """Convert a GitHub search result into a PR dataclass."""
        pull_request = item.pull_request
        merged_at = None
        if pull_request and pull_request.merged_at:
            merged_at = self._to_date(pull_request.merged_at)

        login = item.user.login
        return PR(
            title=item.title,
            number=item.number,
            url=item.html_url,
            author=Author(github_username=login, name=login),
            created_at=self._to_date(item.created_at),
            merged_at=merged_at,
            state=STATE_OPEN if item.state == STATE_OPEN else STATE_CLOSED,
            repo=repo_full_name,
        )

    def _issue_from_search_result(self, item, repo_full_name: str) -> Issue:
        """Convert a GitHub search result into an Issue dataclass."""
        login = item.user.login
        return Issue(
            title=item.title,
            number=item.number,
            url=item.html_url,
            author=Author(github_username=login, name=login),
            created_at=self._to_date(item.created_at),
            state=STATE_OPEN if item.state == STATE_OPEN else STATE_CLOSED,
            repo=repo_full_name,
        )

    def _build_allowed_repos_and_scope_terms(
        self, repos: list[dict]
    ) -> tuple[set[str], list[str]]:
        """Build the set of allowed repos and corresponding search scope terms."""
        allowed_repos: set[str] = set()
        scope_terms: list[str] = []

        for repo_config in repos:
            owner = repo_config["owner"]
            configured_repos = repo_config["repos"]

            if configured_repos == ["*"]:
                resolved = self._resolve_wildcard_repos(owner)
                for repo_name in resolved:
                    allowed_repos.add(f"{owner}/{repo_name}".lower())
                scope_terms.append(f"org:{owner}")
            else:
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
        """Collect PRs from a single repository for the given users and date range."""
        repo_full_name = f"{owner}/{repo_name}"
        queries = self._build_search_queries(
            scope_terms=[f"repo:{repo_full_name}"],
            usernames=usernames,
            item_type="pr",
            start_date=start_date,
            end_date=end_date,
        )
        prs: list[PR] = []

        for query in queries:
            logger.debug("Searching: %s", query)
            for item in self.github.search_issues(query):
                pr = self._pr_from_search_result(item, repo_full_name)
                prs.append(pr)
                logger.debug(
                    "Found PR #%d by %s (merged: %s)",
                    item.number,
                    item.user.login,
                    pr.is_merged,
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
        """Collect issues from a single repository for the given users and date range."""
        repo_full_name = f"{owner}/{repo_name}"
        queries = self._build_search_queries(
            scope_terms=[f"repo:{repo_full_name}"],
            usernames=usernames,
            item_type="issue",
            start_date=start_date,
            end_date=end_date,
        )
        issues: list[Issue] = []

        for query in queries:
            logger.debug("Searching: %s", query)
            for item in self.github.search_issues(query):
                issues.append(self._issue_from_search_result(item, repo_full_name))
                logger.debug("Found issue #%d by %s", item.number, item.user.login)

        return issues

    def _resolve_wildcard_repos(self, owner: str) -> list[str]:
        """Fetch all source (non-fork) repository names for an organization."""
        logger.info("Resolving wildcard repositories for %s", owner)
        org = self.github.get_organization(owner)
        repo_names = [repo.name for repo in org.get_repos(type="sources")]
        logger.info("Found %d repos for %s", len(repo_names), owner)
        return repo_names

    def collect_all_stats(
        self, repos: list[dict], usernames: list[str], start_date: date, end_date: date
    ) -> StatsReport:
        """
        Collect PR and issue stats across multiple repositories.

        Searches GitHub for all PRs/issues by the given users in the date range,
        then filters results to only the configured repositories.
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

        for query in pr_queries:
            logger.debug("Searching PRs: %s", query)
            for item in self.github.search_issues(query):
                repo_full_name = self._get_repo_full_name(item)
                if repo_full_name.lower() not in allowed_repos:
                    continue

                pr = self._pr_from_search_result(item, repo_full_name)
                report.prs.append(pr)
                logger.debug(
                    "Found PR #%d in %s (merged: %s)",
                    item.number,
                    repo_full_name.lower(),
                    pr.is_merged,
                )

        for query in issue_queries:
            logger.debug("Searching issues: %s", query)
            for item in self.github.search_issues(query):
                repo_full_name = self._get_repo_full_name(item)
                if repo_full_name.lower() not in allowed_repos:
                    continue

                report.issues.append(
                    self._issue_from_search_result(item, repo_full_name)
                )
                logger.debug(
                    "Found issue #%d in %s", item.number, repo_full_name.lower()
                )

        logger.info(
            "Collection complete: %d PRs, %d issues",
            len(report.prs),
            len(report.issues),
        )
        return report
