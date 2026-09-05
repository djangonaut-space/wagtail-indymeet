"""Evaluate submissions for Djangonaut Space's "make_toast" contribution tutorial.

The diff is taken against the canonical ``django/django`` repo's ``main``,
not the fork's own default branch. Comparing against the always-current
upstream ``main`` instead means the diff is just whatever the participant
actually changed, however old their fork is.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlparse

from django.conf import settings
from github import Auth, Github, GithubException
from github.File import File
from urllib3.util.retry import Retry

FUNCTION_NAME = "make_toast"
EXPECTED_RETURN_VALUE = "toast"
SHORTCUTS_PATH = "django/shortcuts.py"
# The tutorial only calls for touching django/shortcuts.py, a test file, and
# (optionally) a docs file — anything beyond that suggests unrelated changes
# got swept into the diff.
MAX_EXPECTED_FILES = 3

UPSTREAM_REPO = "django/django"
UPSTREAM_BRANCH = "main"

_BASE_BRANCH_NAMES = re.compile(r"^(main|master|stable/.*)$")


class Reason(StrEnum):
    """Every independent way a submission can fall short (or need a human look)."""

    NOT_ATTEMPTED = "not_attempted"
    SHORTCUTS_NOT_MODIFIED = "shortcuts_not_modified"
    FUNCTION_MISSING = "function_missing"
    WRONG_RETURN_VALUE = "wrong_return_value"
    MISSING_TEST = "missing_test"
    MISSING_DOCS = "missing_docs"
    EXTRA_FILES_MODIFIED = "extra_files_modified"
    UNPARSEABLE_LINK = "unparseable_link"
    AMBIGUOUS_BRANCH = "ambiguous_branch"
    API_ERROR = "api_error"


# Reasons that mean there's no real submission to grade at all, so they
# always make the result incorrect regardless of what else was checked.
_ALWAYS_INCORRECT_REASONS = frozenset(
    {Reason.NOT_ATTEMPTED, Reason.SHORTCUTS_NOT_MODIFIED}
)
# Reasons that, on their own, make the submission incorrect.
_FAILING_REASONS = _ALWAYS_INCORRECT_REASONS | frozenset(
    {
        Reason.FUNCTION_MISSING,
        Reason.WRONG_RETURN_VALUE,
        Reason.MISSING_TEST,
        Reason.EXTRA_FILES_MODIFIED,
    }
)
# Reasons that make it incomplete rather than wrong.
_PARTIAL_REASONS = frozenset({Reason.MISSING_DOCS})
# Reasons that mean this couldn't be evaluated at all, rather than any
# judgment about the submission itself.
_UNCERTAIN_REASONS = frozenset(
    {Reason.UNPARSEABLE_LINK, Reason.AMBIGUOUS_BRANCH, Reason.API_ERROR}
)
# A submission that was actually attempted is only downgraded to incorrect
# (rather than partial) once more than this many failing/missing reasons hit.
_PARTIAL_REASON_LIMIT = 3

# Mirrors home.models.tutorial_evaluation.Result without importing
# Django models into this integration module.
INCORRECT = -1
PARTIAL = 0
CORRECT = 1
UNCERTAIN = 2


@dataclass(frozen=True)
class SubmissionRef:
    """A parsed submission link: a repo, plus a branch or a PR number."""

    owner: str
    repo: str
    ref: str | None = None
    pr_number: int | None = None


@dataclass(frozen=True)
class SubmissionResult:
    """The result of evaluating one applicant's tutorial submission."""

    link: str
    result: int  # INCORRECT, PARTIAL, CORRECT, or UNCERTAIN (module constants above)
    reasons: tuple[Reason, ...]
    notes: str


class SubmissionLinkError(ValueError):
    """Raised when a submission link can't be resolved to a repo/branch/PR."""


def parse_submission_link(link: str) -> SubmissionRef:
    """Parse a github.com URL into the repo and branch/PR it points at.

    Handles the shapes participants actually submit: ``/tree/<branch>``,
    ``/pull/<number>``, ``/pull/new/<branch>`` (branch pushed, no PR opened
    yet), ``/compare/<base>...<owner>:<repo>:<branch>``, and a bare repo URL
    with no ref at all.
    """
    parsed = urlparse(link.strip())
    if parsed.netloc != "github.com":
        raise SubmissionLinkError(f"Not a github.com link: {link}")

    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2:
        raise SubmissionLinkError(f"Could not parse owner/repo from link: {link}")

    owner, repo = parts[0], parts[1]
    rest = parts[2:]

    if not rest:
        return SubmissionRef(owner=owner, repo=repo)

    kind = rest[0]

    if kind == "tree" and len(rest) >= 2:
        return SubmissionRef(owner=owner, repo=repo, ref="/".join(rest[1:]))

    if kind == "pull" and len(rest) >= 2:
        if rest[1] == "new" and len(rest) >= 3:
            return SubmissionRef(owner=owner, repo=repo, ref="/".join(rest[2:]))
        if rest[1].isdigit():
            return SubmissionRef(owner=owner, repo=repo, pr_number=int(rest[1]))

    if kind == "compare" and len(rest) >= 2:
        spec = "/".join(rest[1:])
        head = spec.split("...", 1)[-1] if "..." in spec else spec.split("..", 1)[-1]
        head_parts = head.split(":")
        if len(head_parts) == 3:
            head_owner, head_repo, head_branch = head_parts
            return SubmissionRef(owner=head_owner, repo=head_repo, ref=head_branch)
        if len(head_parts) == 2:
            head_owner, head_branch = head_parts
            return SubmissionRef(owner=head_owner, repo=repo, ref=head_branch)
        return SubmissionRef(owner=owner, repo=repo, ref=head)

    raise SubmissionLinkError(f"Unrecognized GitHub link shape: {link}")


def _create_client(github_token: str | None = None) -> Github:
    token = github_token or settings.GITHUB_TOKEN
    if not token:
        raise ValueError("GitHub token is required. Set GITHUB_TOKEN in settings.")
    # PyGithub's default GithubRetry sleeps on rate-limit 403s; swap for a
    # plain no-retry Retry so rate limiting surfaces as an exception instead
    # of silently stalling a batch evaluation run.
    return Github(auth=Auth.Token(token), retry=Retry(total=0))


def _added_lines(patch: str | None) -> str:
    """Return only the added (``+``) lines of a unified diff patch.

    Restricting to added lines keeps the regexes below from matching
    unrelated ``return`` statements sitting in unchanged context lines
    elsewhere in the file.
    """
    if not patch:
        return ""
    return "\n".join(
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    )


def _extract_return_value(added_lines: str, function_name: str) -> str | None:
    """Return the literal string a function's first ``return`` statement returns, if any."""
    idx = added_lines.find(f"def {function_name}(")
    if idx == -1:
        return None
    match = re.search(r"return\s+['\"]([^'\"]*)['\"]", added_lines[idx:])
    return match.group(1) if match else None


def _has_matching_test(files: dict[str, File]) -> bool:
    for file in files.values():
        added = _added_lines(file.patch)
        if (
            f"{FUNCTION_NAME}(" in added
            and EXPECTED_RETURN_VALUE in added
            and re.search(r"assert\w*\(", added)
        ):
            return True
    return False


def _has_docs(files: dict[str, File]) -> bool:
    return any(
        filename.startswith("docs/") and FUNCTION_NAME in _added_lines(file.patch)
        for filename, file in files.items()
    )


def _result_for(reasons: frozenset[Reason]) -> int:
    if reasons & _UNCERTAIN_REASONS:
        return UNCERTAIN
    if reasons & _ALWAYS_INCORRECT_REASONS:
        return INCORRECT
    hit = reasons & (_FAILING_REASONS | _PARTIAL_REASONS)
    if not hit:
        return CORRECT
    if len(hit) <= _PARTIAL_REASON_LIMIT:
        return PARTIAL
    return INCORRECT


def _build_evaluation(link: str, messages: dict[Reason, str]) -> SubmissionResult:
    reasons = tuple(messages)
    result = _result_for(frozenset(reasons))
    notes = (
        " ".join(messages.values())
        if messages
        else (
            f"{FUNCTION_NAME}() returns {EXPECTED_RETURN_VALUE!r} and is covered "
            "by a matching test and documentation."
        )
    )
    return SubmissionResult(link=link, result=result, reasons=reasons, notes=notes)


def _evaluate_files(link: str, files: dict[str, File]) -> SubmissionResult:
    """Check every independent tutorial requirement and collect all that fail.

    A submission is often wrong in more than one way at once (e.g. no test
    *and* no docs), so this doesn't stop at the first problem found — the
    caller gets the full picture, and ``result`` is derived from the worst
    reason present.
    """
    if not files:
        return _build_evaluation(
            link,
            {
                Reason.NOT_ATTEMPTED: (
                    f"No changes were found relative to {UPSTREAM_REPO}'s "
                    f"{UPSTREAM_BRANCH}; the tutorial doesn't appear to have "
                    "been attempted."
                )
            },
        )

    shortcuts_file = files.get(SHORTCUTS_PATH)
    if shortcuts_file is None:
        return _build_evaluation(
            link, {Reason.SHORTCUTS_NOT_MODIFIED: f"{SHORTCUTS_PATH} was not modified."}
        )

    added = _added_lines(shortcuts_file.patch)
    messages: dict[Reason, str] = {}

    if f"def {FUNCTION_NAME}(" not in added:
        messages[Reason.FUNCTION_MISSING] = (
            f"{FUNCTION_NAME}() was not added to {SHORTCUTS_PATH}."
        )
    else:
        return_value = _extract_return_value(added, FUNCTION_NAME)
        if return_value != EXPECTED_RETURN_VALUE:
            detail = (
                f"returns {return_value!r} instead"
                if return_value
                else "its return value could not be confirmed as a plain string"
            )
            messages[Reason.WRONG_RETURN_VALUE] = (
                f"{FUNCTION_NAME}() was added but does not return the string "
                f"{EXPECTED_RETURN_VALUE!r} as specified ({detail})."
            )

    if not _has_matching_test(files):
        messages[Reason.MISSING_TEST] = (
            f"No test asserting {FUNCTION_NAME}() returns {EXPECTED_RETURN_VALUE!r} was found."
        )

    if not _has_docs(files):
        messages[Reason.MISSING_DOCS] = (
            "No documentation changes (release note / topic doc) were found."
        )

    if len(files) > MAX_EXPECTED_FILES:
        messages[Reason.EXTRA_FILES_MODIFIED] = (
            f"{len(files)} files were changed, but only {SHORTCUTS_PATH}, a test "
            "file, and a docs file are expected; unrelated changes may have been "
            "included."
        )

    return _build_evaluation(link, messages)


def evaluate_submission(
    link: str, *, github_token: str | None = None
) -> SubmissionResult:
    """Evaluate one applicant's make_toast tutorial submission.

    Resolves ``link`` (a fork's branch, PR, or compare URL) to an
    ``owner:branch``, diffs that against ``django/django``'s ``main``, and
    checks whether ``make_toast()`` was implemented correctly in
    ``django/shortcuts.py``, with a matching test, ideally documentation, and
    without unrelated files swept into the diff — collecting every
    independent problem found rather than stopping at the first one, since
    submissions often fail in more than one way at once. A submission that
    was genuinely attempted is marked partial rather than incorrect as long
    as at most ``_PARTIAL_REASON_LIMIT`` of those problems were hit. Never
    raises for GitHub-side failures (missing repo, missing branch, rate
    limiting, ...) or unparseable links — those come back as an ``UNCERTAIN``
    evaluation instead, so this can run unattended over a batch of
    submissions.
    """
    try:
        ref = parse_submission_link(link)
    except SubmissionLinkError as exc:
        return _build_evaluation(link, {Reason.UNPARSEABLE_LINK: str(exc)})

    try:
        client = _create_client(github_token)
        owner, branch = ref.owner, ref.ref

        if ref.pr_number is not None:
            fork_repo = client.get_repo(f"{ref.owner}/{ref.repo}")
            pr = fork_repo.get_pull(ref.pr_number)
            if pr.head.repo is None:
                return _build_evaluation(
                    link,
                    {Reason.API_ERROR: "The PR's source fork no longer exists."},
                )
            owner, branch = pr.head.repo.owner.login, pr.head.ref

        elif branch is None:
            fork_repo = client.get_repo(f"{ref.owner}/{ref.repo}")
            candidates = [
                b.name
                for b in fork_repo.get_branches()
                if b.name != fork_repo.default_branch
                and not _BASE_BRANCH_NAMES.match(b.name)
            ]
            if len(candidates) != 1:
                found = ", ".join(candidates) if candidates else "none"
                return _build_evaluation(
                    link,
                    {
                        Reason.AMBIGUOUS_BRANCH: (
                            "No branch was given in the link and none could be "
                            f"inferred: non-default branches found on {ref.owner}/{ref.repo}: "
                            f"{found}."
                        )
                    },
                )
            branch = candidates[0]

        upstream = client.get_repo(UPSTREAM_REPO)
        comparison = upstream.compare(UPSTREAM_BRANCH, f"{owner}:{branch}")
        files = {f.filename: f for f in comparison.files or []}
        return _evaluate_files(link, files)

    except GithubException as exc:
        return _build_evaluation(
            link,
            {
                Reason.API_ERROR: f"GitHub API error while evaluating this submission: {exc}"
            },
        )
