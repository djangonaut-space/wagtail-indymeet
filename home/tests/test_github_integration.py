"""Tests for the make_toast tutorial evaluator in home.integrations.github."""

from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from github import GithubException

from home.integrations.github import (
    CORRECT,
    INCORRECT,
    PARTIAL,
    UNCERTAIN,
    UPSTREAM_BRANCH,
    UPSTREAM_REPO,
    Reason,
    SubmissionLinkError,
    SubmissionRef,
    evaluate_submission,
    parse_submission_link,
)

FUNCTION_PATCH = """@@ -209,3 +209,6 @@ def resolve_url(to, *args, **kwargs):

     # Finally, fall back and assume it's a URL
     return to
+
+def make_toast():
+    return "toast"
"""

WRONG_VALUE_PATCH = """@@ -209,3 +209,6 @@ def resolve_url(to, *args, **kwargs):
     return to
+
+def make_toast():
+    return "Toast!"
"""

NO_FUNCTION_PATCH = """@@ -26,7 +26,7 @@
 def capfirst(x):
-    return x
+    return "ticket_99999"
"""

TEST_PATCH = """@@ -0,0 +1,7 @@
+from django.shortcuts import make_toast
+from django.test import SimpleTestCase
+
+
+class MakeToastTests(SimpleTestCase):
+    def test_make_toast(self):
+        self.assertEqual(make_toast(), "toast")
"""

DOCS_PATCH = """@@ -294,3 +294,9 @@
+``make_toast()``
+================
+
+.. function:: make_toast()
+
+Returns ``'toast'``.
"""

RELEASE_NOTES_PATCH = """@@ -34,6 +34,10 @@ What's new in Django 6.2
+:mod:`django.shortcuts`
+~~~~~~~~~~~~~~~~~~~~~~~
+
+* The new :func:`django.shortcuts.make_toast` function returns ``'toast'``.
"""


def _file(filename: str, patch: str | None) -> Mock:
    return Mock(filename=filename, patch=patch)


def _branch(name: str) -> Mock:
    # Mock(name=...) sets the mock's repr, not a `.name` attribute — it has
    # to be assigned afterward.
    branch = Mock()
    branch.name = name
    return branch


class ParseSubmissionLinkTests(SimpleTestCase):
    def test_tree_link(self):
        ref = parse_submission_link("https://github.com/alice/django/tree/ticket_99999")
        self.assertEqual(
            ref, SubmissionRef(owner="alice", repo="django", ref="ticket_99999")
        )

    def test_bare_repo_link(self):
        ref = parse_submission_link("https://github.com/alice/django")
        self.assertEqual(ref, SubmissionRef(owner="alice", repo="django"))

    def test_pull_link(self):
        ref = parse_submission_link("https://github.com/alice/django/pull/1")
        self.assertEqual(ref, SubmissionRef(owner="alice", repo="django", pr_number=1))

    def test_pull_new_link(self):
        ref = parse_submission_link(
            "https://github.com/alice/django/pull/new/ticket_99999"
        )
        self.assertEqual(
            ref, SubmissionRef(owner="alice", repo="django", ref="ticket_99999")
        )

    def test_compare_link_with_owner_repo_branch_head(self):
        ref = parse_submission_link(
            "https://github.com/django/django/compare/main...alice:django:ticket_99999"
        )
        self.assertEqual(
            ref, SubmissionRef(owner="alice", repo="django", ref="ticket_99999")
        )

    def test_compare_link_with_owner_branch_head(self):
        ref = parse_submission_link(
            "https://github.com/alice/django/compare/main...alice:ticket_99999"
        )
        self.assertEqual(
            ref, SubmissionRef(owner="alice", repo="django", ref="ticket_99999")
        )

    def test_non_github_link_raises(self):
        with self.assertRaises(SubmissionLinkError):
            parse_submission_link("https://gitlab.com/alice/django/tree/ticket_99999")

    def test_link_missing_repo_raises(self):
        with self.assertRaises(SubmissionLinkError):
            parse_submission_link("https://github.com/alice")


class EvaluateSubmissionTests(SimpleTestCase):
    def _mock_upstream(self, mock_github_class) -> Mock:
        """Set up get_repo so only the upstream django/django repo is ever fetched.

        Tree/compare links carry an explicit branch, so evaluation never
        needs to look at the fork itself — only PR and bare-repo links do
        (see ``_mock_fork_and_upstream``).
        """
        upstream = Mock()
        mock_github_class.return_value.get_repo.return_value = upstream
        return upstream

    def _mock_fork_and_upstream(self, mock_github_class) -> tuple[Mock, Mock]:
        fork, upstream = Mock(), Mock()

        def get_repo(full_name):
            return upstream if full_name == UPSTREAM_REPO else fork

        mock_github_class.return_value.get_repo.side_effect = get_repo
        return fork, upstream

    @patch("home.integrations.github.Github")
    def test_no_changes_is_not_attempted(self, mock_github_class):
        upstream = self._mock_upstream(mock_github_class)
        upstream.compare.return_value = Mock(files=[])

        result = evaluate_submission(
            "https://github.com/alice/django/tree/ticket_99999", github_token="t"
        )

        self.assertEqual(result.result, INCORRECT)
        self.assertEqual(result.reasons, (Reason.NOT_ATTEMPTED,))
        self.assertIn("doesn't appear to have been attempted", result.notes)

    @patch("home.integrations.github.Github")
    def test_diffs_against_upstream_main_not_the_forks_own(self, mock_github_class):
        """Regression: the fork's own (possibly stale) main must never be used as the base."""
        upstream = self._mock_upstream(mock_github_class)
        upstream.compare.return_value = Mock(files=[])

        evaluate_submission(
            "https://github.com/alice/django/tree/ticket_99999", github_token="t"
        )

        mock_github_class.return_value.get_repo.assert_called_once_with(UPSTREAM_REPO)
        upstream.compare.assert_called_once_with(UPSTREAM_BRANCH, "alice:ticket_99999")

    @patch("home.integrations.github.Github")
    def test_shortcuts_not_touched(self, mock_github_class):
        upstream = self._mock_upstream(mock_github_class)
        upstream.compare.return_value = Mock(
            files=[_file("django/utils/text.py", NO_FUNCTION_PATCH)]
        )

        result = evaluate_submission(
            "https://github.com/alice/django/tree/ticket_99999", github_token="t"
        )

        self.assertEqual(result.result, INCORRECT)
        self.assertEqual(result.reasons, (Reason.SHORTCUTS_NOT_MODIFIED,))
        self.assertIn("was not modified", result.notes)

    @patch("home.integrations.github.Github")
    def test_wrong_return_value_also_reports_missing_test_and_docs(
        self, mock_github_class
    ):
        """Three failing/missing reasons at once is still within the partial threshold."""
        upstream = self._mock_upstream(mock_github_class)
        upstream.compare.return_value = Mock(
            files=[_file("django/shortcuts.py", WRONG_VALUE_PATCH)]
        )

        result = evaluate_submission(
            "https://github.com/alice/django/tree/ticket_99999", github_token="t"
        )

        self.assertEqual(result.result, PARTIAL)
        self.assertEqual(
            set(result.reasons),
            {Reason.WRONG_RETURN_VALUE, Reason.MISSING_TEST, Reason.MISSING_DOCS},
        )
        self.assertIn("does not return the string", result.notes)
        self.assertIn("No test asserting", result.notes)
        self.assertIn("Missing a topic doc entry", result.notes)
        self.assertIn("a release note", result.notes)

    @patch("home.integrations.github.Github")
    def test_correct_function_without_test_or_docs_reports_both(
        self, mock_github_class
    ):
        upstream = self._mock_upstream(mock_github_class)
        upstream.compare.return_value = Mock(
            files=[_file("django/shortcuts.py", FUNCTION_PATCH)]
        )

        result = evaluate_submission(
            "https://github.com/alice/django/tree/ticket_99999", github_token="t"
        )

        self.assertEqual(result.result, PARTIAL)
        self.assertEqual(
            set(result.reasons), {Reason.MISSING_TEST, Reason.MISSING_DOCS}
        )

    @patch("home.integrations.github.Github")
    def test_correct_function_and_test_without_docs(self, mock_github_class):
        upstream = self._mock_upstream(mock_github_class)
        upstream.compare.return_value = Mock(
            files=[
                _file("django/shortcuts.py", FUNCTION_PATCH),
                _file("tests/shortcuts/test_make_toast.py", TEST_PATCH),
            ]
        )

        result = evaluate_submission(
            "https://github.com/alice/django/tree/ticket_99999", github_token="t"
        )

        self.assertEqual(result.result, PARTIAL)
        self.assertEqual(result.reasons, (Reason.MISSING_DOCS,))
        self.assertIn("Missing a topic doc entry", result.notes)

    @patch("home.integrations.github.Github")
    def test_fully_correct_submission(self, mock_github_class):
        upstream = self._mock_upstream(mock_github_class)
        upstream.compare.return_value = Mock(
            files=[
                _file("django/shortcuts.py", FUNCTION_PATCH),
                _file("tests/shortcuts/test_make_toast.py", TEST_PATCH),
                _file("docs/topics/http/shortcuts.txt", DOCS_PATCH),
                _file("docs/releases/6.2.txt", RELEASE_NOTES_PATCH),
            ]
        )

        result = evaluate_submission(
            "https://github.com/alice/django/tree/ticket_99999", github_token="t"
        )

        self.assertEqual(result.result, CORRECT)
        self.assertEqual(result.reasons, ())

    @patch("home.integrations.github.Github")
    def test_release_notes_filename_is_not_tied_to_a_version_scheme(
        self, mock_github_class
    ):
        """The release notes filename check must survive Django's next versioning scheme.

        Django names release note files after its version (e.g. ``6.2.txt``
        today), and that scheme is expected to change (e.g. to calendar
        versioning like ``2028.txt`` or ``2028.0.txt``) — the check must not
        assume any particular filename shape beyond living in docs/releases/.
        """
        upstream = self._mock_upstream(mock_github_class)
        upstream.compare.return_value = Mock(
            files=[
                _file("django/shortcuts.py", FUNCTION_PATCH),
                _file("tests/shortcuts/test_make_toast.py", TEST_PATCH),
                _file("docs/topics/http/shortcuts.txt", DOCS_PATCH),
                _file("docs/releases/2028.0.txt", RELEASE_NOTES_PATCH),
            ]
        )

        result = evaluate_submission(
            "https://github.com/alice/django/tree/ticket_99999", github_token="t"
        )

        self.assertEqual(result.result, CORRECT)
        self.assertEqual(result.reasons, ())

    @patch("home.integrations.github.Github")
    def test_extra_files_partial(self, mock_github_class):
        """An otherwise-correct submission with one unrelated file is partial, not incorrect."""
        upstream = self._mock_upstream(mock_github_class)
        upstream.compare.return_value = Mock(
            files=[
                _file("django/shortcuts.py", FUNCTION_PATCH),
                _file("tests/shortcuts/test_make_toast.py", TEST_PATCH),
                _file("docs/topics/http/shortcuts.txt", DOCS_PATCH),
                _file("docs/releases/6.2.txt", RELEASE_NOTES_PATCH),
                _file("django/utils/text.py", NO_FUNCTION_PATCH),
            ]
        )

        result = evaluate_submission(
            "https://github.com/alice/django/tree/ticket_99999", github_token="t"
        )

        self.assertEqual(result.result, PARTIAL)
        self.assertEqual(result.reasons, (Reason.EXTRA_FILES_MODIFIED,))
        self.assertIn("5 files were changed", result.notes)

    @patch("home.integrations.github.Github")
    def test_too_many_reasons_incorrect(self, mock_github_class):
        """Four failing/missing reasons at once exceeds the partial threshold."""
        upstream = self._mock_upstream(mock_github_class)
        upstream.compare.return_value = Mock(
            files=[
                _file("django/shortcuts.py", WRONG_VALUE_PATCH),
                _file("django/utils/text.py", NO_FUNCTION_PATCH),
                _file("some/other/file.py", NO_FUNCTION_PATCH),
                _file("yet/another/file.py", NO_FUNCTION_PATCH),
                _file("still/another/file.py", NO_FUNCTION_PATCH),
            ]
        )

        result = evaluate_submission(
            "https://github.com/alice/django/tree/ticket_99999", github_token="t"
        )

        self.assertEqual(result.result, INCORRECT)
        self.assertEqual(
            set(result.reasons),
            {
                Reason.WRONG_RETURN_VALUE,
                Reason.MISSING_TEST,
                Reason.MISSING_DOCS,
                Reason.EXTRA_FILES_MODIFIED,
            },
        )

    @patch("home.integrations.github.Github")
    def test_pull_request_link_compares_pr_head_owner_and_branch(
        self, mock_github_class
    ):
        fork, upstream = self._mock_fork_and_upstream(mock_github_class)
        pr = Mock()
        pr.head.repo.owner.login = "alice"
        pr.head.ref = "ticket_99999"
        fork.get_pull.return_value = pr
        upstream.compare.return_value = Mock(
            files=[
                _file("django/shortcuts.py", FUNCTION_PATCH),
                _file("tests/shortcuts/test_make_toast.py", TEST_PATCH),
            ]
        )

        result = evaluate_submission(
            "https://github.com/alice/django/pull/1", github_token="t"
        )

        self.assertEqual(result.result, PARTIAL)
        self.assertEqual(result.reasons, (Reason.MISSING_DOCS,))
        fork.get_pull.assert_called_once_with(1)
        upstream.compare.assert_called_once_with(UPSTREAM_BRANCH, "alice:ticket_99999")

    @patch("home.integrations.github.Github")
    def test_pull_request_with_deleted_source_fork_is_uncertain(
        self, mock_github_class
    ):
        fork, _upstream = self._mock_fork_and_upstream(mock_github_class)
        pr = Mock()
        pr.head.repo = None
        fork.get_pull.return_value = pr

        result = evaluate_submission(
            "https://github.com/alice/django/pull/1", github_token="t"
        )

        self.assertEqual(result.result, UNCERTAIN)
        self.assertEqual(result.reasons, (Reason.API_ERROR,))

    @patch("home.integrations.github.Github")
    def test_bare_repo_link_resolves_single_candidate_branch(self, mock_github_class):
        fork, upstream = self._mock_fork_and_upstream(mock_github_class)
        fork.default_branch = "main"
        fork.get_branches.return_value = [_branch("main"), _branch("ticket_99999")]
        upstream.compare.return_value = Mock(
            files=[
                _file("django/shortcuts.py", FUNCTION_PATCH),
                _file("tests/shortcuts/test_make_toast.py", TEST_PATCH),
                _file("docs/topics/http/shortcuts.txt", DOCS_PATCH),
                _file("docs/releases/6.2.txt", RELEASE_NOTES_PATCH),
            ]
        )

        result = evaluate_submission(
            "https://github.com/alice/django", github_token="t"
        )

        self.assertEqual(result.result, CORRECT)
        upstream.compare.assert_called_once_with(UPSTREAM_BRANCH, "alice:ticket_99999")

    @patch("home.integrations.github.Github")
    def test_bare_repo_link_with_no_extra_branch_is_uncertain(self, mock_github_class):
        fork, _upstream = self._mock_fork_and_upstream(mock_github_class)
        fork.default_branch = "main"
        fork.get_branches.return_value = [_branch("main")]

        result = evaluate_submission(
            "https://github.com/alice/django", github_token="t"
        )

        self.assertEqual(result.result, UNCERTAIN)
        self.assertEqual(result.reasons, (Reason.AMBIGUOUS_BRANCH,))
        self.assertIn("No branch was given", result.notes)

    def test_unparseable_link_is_uncertain(self):
        result = evaluate_submission(
            "https://gitlab.com/alice/django", github_token="t"
        )

        self.assertEqual(result.result, UNCERTAIN)
        self.assertEqual(result.reasons, (Reason.UNPARSEABLE_LINK,))

    @patch("home.integrations.github.Github")
    def test_github_api_error_is_uncertain(self, mock_github_class):
        mock_github_class.return_value.get_repo.side_effect = GithubException(
            404, {"message": "Not Found"}, {}
        )

        result = evaluate_submission(
            "https://github.com/alice/django/tree/ticket_99999", github_token="t"
        )

        self.assertEqual(result.result, UNCERTAIN)
        self.assertEqual(result.reasons, (Reason.API_ERROR,))
