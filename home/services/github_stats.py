"""GitHub stats collection service for Djangonaut Space sessions."""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from functools import cached_property

from django.conf import settings
from github import Github
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

STATE_OPEN = "open"
STATE_CLOSED = "closed"


@dataclass(frozen=True)
class Author:
    github_username: str
    name: str


@dataclass(frozen=True)
class TeamScope:
    """A team's GitHub search scope paired with its members.

    One scope produces one set of queries (PRs created, PRs merged, issues)
    per member. ``scope_term`` is a GitHub search qualifier such as
    ``repo:owner/name`` or ``org:owner``.
    """

    scope_term: str
    members: tuple[Author, ...]
    label: str = ""


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
class TeamReport:
    """PRs and issues collected for a single team scope."""

    label: str
    scope_term: str
    prs: list[PR] = field(default_factory=list)
    issues: list[Issue] = field(default_factory=list)

    @property
    def merged_prs(self) -> list[PR]:
        return [pr for pr in self.prs if pr.is_merged]

    @property
    def closed_prs(self) -> list[PR]:
        return [pr for pr in self.prs if pr.is_closed]

    @property
    def open_prs(self) -> list[PR]:
        return [pr for pr in self.prs if pr.is_open]

    @property
    def open_issues(self) -> list[Issue]:
        return [issue for issue in self.issues if issue.is_open]

    @property
    def has_activity(self) -> bool:
        return bool(self.prs or self.issues)


@dataclass
class StatsReport:
    """Aggregates GitHub statistics for a date range, grouped by team."""

    start_date: date
    end_date: date
    teams: list[TeamReport] = field(default_factory=list)

    @cached_property
    def authors(self) -> set[Author]:
        authors: set[Author] = set()
        for team in self.teams:
            authors.update(pr.author for pr in team.prs)
            authors.update(issue.author for issue in team.issues)
        return authors

    def count_open_prs(self) -> int:
        return sum(len(t.open_prs) for t in self.teams)

    def count_merged_prs(self) -> int:
        return sum(len(t.merged_prs) for t in self.teams)

    def count_closed_prs(self) -> int:
        return sum(len(t.closed_prs) for t in self.teams)

    def count_open_issues(self) -> int:
        return sum(len(t.open_issues) for t in self.teams)

    @property
    def has_activity(self) -> bool:
        return any(t.has_activity for t in self.teams)


class GitHubStatsCollector:
    """Collects GitHub PR and Issue statistics using the GitHub Search API."""

    def __init__(self, github_token: str | None = None):
        token = github_token or settings.GITHUB_TOKEN
        if not token:
            raise ValueError("GitHub token is required. Set GITHUB_TOKEN in settings.")

        # PyGithub's default GithubRetry sleeps on rate-limit 403s; swap for a
        # plain no-retry Retry so rate limiting surfaces as an exception
        # instead of a silent wait.
        self.github = Github(token, retry=Retry(total=0))
        logger.info("GitHubStatsCollector initialized (retries disabled)")

    def _to_date(self, dt: datetime | date | None) -> date | None:
        """Convert a datetime to a date, passing through date and None unchanged."""
        if isinstance(dt, datetime):
            return dt.date()
        return dt

    def _get_repo_full_name(self, item) -> str:
        """Parse ``owner/name`` from the search result's ``repository_url``.

        Using the URL avoids an extra API round-trip that ``item.repository.full_name``
        would cost (lazy attribute fetch).
        """
        return item.repository_url.split("/repos/", 1)[1]

    def _item_kwargs(self, item, repo_full_name: str, author: Author) -> dict:
        """Fields shared by ``PR`` and ``Issue`` constructed from a search result."""
        return dict(
            title=item.title,
            number=item.number,
            url=item.html_url,
            author=author,
            created_at=self._to_date(item.created_at),
            state=STATE_OPEN if item.state == STATE_OPEN else STATE_CLOSED,
            repo=repo_full_name,
        )

    def _pr_from_search_result(self, item, repo_full_name: str, author: Author) -> PR:
        return PR(
            **self._item_kwargs(item, repo_full_name, author),
            merged_at=self._to_date(item.pull_request.merged_at),
        )

    def _issue_from_search_result(
        self, item, repo_full_name: str, author: Author
    ) -> Issue:
        return Issue(**self._item_kwargs(item, repo_full_name, author))

    def _collect_scope_prs(
        self,
        scope: TeamScope,
        start_date: date,
        end_date: date,
        team_report: TeamReport,
    ) -> None:
        """Fetch PRs for one team scope into its ``TeamReport``.

        One query per (member, qualifier) — GitHub Search does NOT support
        OR'd ``author:`` clauses (returns 422). Both ``created:`` and
        ``merged:`` are queried so PRs merged inside the window are counted
        even when opened earlier; results are deduplicated by ``(repo,
        number)`` across the two.
        """
        seen: set[tuple[str, int]] = set()
        for member in scope.members:
            for qualifier in ("created", "merged"):
                query = (
                    f"{scope.scope_term} author:{member.github_username} "
                    f"type:pr {qualifier}:{start_date}..{end_date}"
                )
                logger.info("Searching PRs (%s): %s", qualifier, query)
                for item in self.github.search_issues(query):
                    repo_full_name = self._get_repo_full_name(item)
                    key = (repo_full_name.lower(), item.number)
                    if key in seen:
                        continue
                    seen.add(key)
                    team_report.prs.append(
                        self._pr_from_search_result(item, repo_full_name, member)
                    )

    def _collect_scope_issues(
        self,
        scope: TeamScope,
        start_date: date,
        end_date: date,
        team_report: TeamReport,
    ) -> None:
        """Fetch issues for one team scope into its ``TeamReport``."""
        for member in scope.members:
            query = (
                f"{scope.scope_term} author:{member.github_username} "
                f"type:issue created:{start_date}..{end_date}"
            )
            logger.info("Searching issues: %s", query)
            for item in self.github.search_issues(query):
                repo_full_name = self._get_repo_full_name(item)
                team_report.issues.append(
                    self._issue_from_search_result(item, repo_full_name, member)
                )

    def collect_all_stats(
        self,
        scopes: list[TeamScope],
        start_date: date,
        end_date: date,
    ) -> StatsReport:
        """Collect PR and issue stats across a list of team scopes.

        Each scope pairs one GitHub search scope (``repo:`` or ``org:``)
        with the members whose contributions should be counted there, so
        queries are both tight (no cross-team noise) and results stay
        naturally grouped by team in the returned report.
        """
        logger.info(
            "Starting stats collection across %d team scopes (%s to %s)",
            len(scopes),
            start_date,
            end_date,
        )

        teams: list[TeamReport] = []
        for scope in scopes:
            logger.debug(
                "Scope %s (%s) with %d members",
                scope.label or scope.scope_term,
                scope.scope_term,
                len(scope.members),
            )
            team_report = TeamReport(label=scope.label, scope_term=scope.scope_term)
            self._collect_scope_prs(scope, start_date, end_date, team_report)
            self._collect_scope_issues(scope, start_date, end_date, team_report)
            teams.append(team_report)

        report = StatsReport(start_date=start_date, end_date=end_date, teams=teams)
        logger.info(
            "Collection complete: %d PRs, %d issues across %d teams",
            sum(len(t.prs) for t in teams),
            sum(len(t.issues) for t in teams),
            len(teams),
        )
        return report
