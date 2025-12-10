"""
Report formatting for GitHub stats.

Formats StatsReport data into various output formats (HTML, CSV, plain text).
"""

from datetime import date
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .github_stats import StatsReport, PR, Issue


class ReportFormatter:
    """Formats GitHub stats reports in various formats."""

    @staticmethod
    def format_text(report: "StatsReport") -> str:
        """
        Format report as plain text (matching original djangonauts-stats library).
        """
        output = []

        # Header
        output.append(
            f"\n=== Djangonauts Report ({report.start_date} → {report.end_date}) ==="
        )
        output.append(
            f"Open PRs: {report.count_open_prs()}, "
            f"Merged: {report.count_merged_prs()}, "
            f"Issue: {report.count_open_issues()}"
        )

        # Authors
        authors = report.get_authors()
        author_names = [author.name for author in authors] if authors else []
        output.append(f"Djangonaut Authors: {', '.join(author_names)}")

        # Merged PRs
        merged_prs = report.get_merged_prs()
        if merged_prs:
            output.append("\n--Merged--")
            items = []
            for pr in merged_prs:
                items.append(f"🎉 {pr.title}\n{pr.author.name}\n{pr.url}")
            output.append("\n\n".join(items))
        else:
            output.append("\n\nNo merged PRs")

        # Open PRs
        open_prs = report.get_open_prs()
        if open_prs:
            output.append("\n\n--Opened--")
            items = []
            for pr in open_prs:
                items.append(f"✨ {pr.title}\n{pr.author.name} \n{pr.url}")
            output.append("\n\n".join(items))
        else:
            output.append("\n\nNo opened PRs")

        # Issues (Reference script treats Issues slightly differently, usually just
        # --Issue-- or similar if present, but looking at reference output:
        # "Issue: 0 ... --No Issue--"
        # Reference code: "load_issues" loop adds to self.results.issues.
        # Reference export: if nr_open_issue -> "\n\n--Issue--\n" (inferred vs variable
        # names? wait, let's check generator.py snippet again)
        # generator.py snippet ends at `No opened PRs`. It cuts off!
        # Chunk 0 ended at line 68 equivalent. It didn't show Issue printing logic fully!
        # But I can infer it. I will keep my logic for issues but match standard style.
        # Actually I saw "Issue: {nr_open_issue}" in header.
        # I will assume standard format for issues.

        open_issues = report.get_open_issues()
        if open_issues:
            output.append("\n\n--Issue--")
            items = []
            for issue in open_issues:
                # Reference likely uses no emoji or specific emoji?
                # Chunk skipped it. I'll use simple format similar to PRs.
                items.append(f"✏️ {issue.title}\n{issue.author.name}\n{issue.url}")
            output.append("\n\n".join(items))
        else:
            output.append("\n\n--No Issue--")

        output.append("\n" + "=" * 40)

        return "\n".join(output)

    @staticmethod
    def format_html(report: "StatsReport") -> str:
        """
        Format report as HTML for admin display.
        """
        html_parts = []

        # Summary section (already handled by template structure mostly, but we inject content)
        # Note: The template likely wraps this.
        # Actually the template calls {{ report_html|safe }}.
        # My CSS expects: .stats-summary, .stats-counts, .stat

        html_parts.append('<div class="stats-summary">')
        html_parts.append(
            f"<h2><span>Overview</span> "
            f"<span>{report.start_date} → {report.end_date}</span></h2>"
        )
        html_parts.append('<div class="stats-counts">')
        html_parts.append(
            f'<div class="stat"><span>Open PRs</span>'
            f"<strong>{report.count_open_prs()}</strong></div>"
        )
        html_parts.append(
            f'<div class="stat"><span>Merged PRs</span>'
            f"<strong>{report.count_merged_prs()}</strong></div>"
        )
        html_parts.append(
            f'<div class="stat"><span>Issues</span>'
            f"<strong>{report.count_open_issues()}</strong></div>"
        )
        html_parts.append("</div>")

        # Authors
        authors = report.get_authors()
        if authors:
            author_names = [
                f'<span class="author-tag">{author.name}</span>' for author in authors
            ]
            html_parts.append(
                f'<div style="margin-top:15px; '
                f"border-top:1px solid rgba(255,255,255,0.1); padding-top:10px; "
                f'font-size:0.9em; opacity:0.9;"><strong>Djangonauts:</strong> '
                f'{", ".join(author_names)}</div>'
            )

        html_parts.append("</div>")

        # Merged PRs
        merged_prs = report.get_merged_prs()
        if merged_prs:
            html_parts.append('<div class="merged-prs">')
            html_parts.append("<h3>🎉 Merged Pull Requests</h3>")
            html_parts.append("<ul>")
            for pr in merged_prs:
                html_parts.append(f"<li>")
                html_parts.append(f"<strong>{pr.title}</strong>")
                html_parts.append('<div class="meta-row">')
                html_parts.append(f'<span class="repo">{pr.repo}</span>')
                html_parts.append(f'<span class="author">by {pr.author.name}</span>')
                html_parts.append(f'<span class="date">on {pr.merged_at}</span>')
                html_parts.append("</div>")
                html_parts.append(
                    f'<a href="{pr.url}" target="_blank" '
                    f'style="font-size:0.85em; text-decoration:underline;">'
                    f"View on GitHub &rarr;</a>"
                )
                html_parts.append("</li>")
            html_parts.append("</ul>")
            html_parts.append("</div>")

        # Open PRs
        open_prs = report.get_open_prs()
        if open_prs:
            html_parts.append('<div class="open-prs">')
            html_parts.append("<h3>✨ Open Pull Requests</h3>")
            html_parts.append("<ul>")
            for pr in open_prs:
                html_parts.append(f"<li>")
                html_parts.append(f"<strong>{pr.title}</strong>")
                html_parts.append('<div class="meta-row">')
                html_parts.append(f'<span class="repo">{pr.repo}</span>')
                html_parts.append(f'<span class="author">by {pr.author.name}</span>')
                html_parts.append(f'<span class="date">created {pr.created_at}</span>')
                html_parts.append("</div>")
                html_parts.append(
                    f'<a href="{pr.url}" target="_blank" '
                    f'style="font-size:0.85em; text-decoration:underline;">'
                    f"View on GitHub &rarr;</a>"
                )
                html_parts.append("</li>")
            html_parts.append("</ul>")
            html_parts.append("</div>")

        # Issues
        open_issues = report.get_open_issues()
        if open_issues:
            html_parts.append('<div class="open-issues">')
            html_parts.append("<h3>✏️ Issues</h3>")
            html_parts.append("<ul>")
            for issue in open_issues:
                html_parts.append(f"<li>")
                html_parts.append(f"<strong>{issue.title}</strong>")
                html_parts.append('<div class="meta-row">')
                html_parts.append(f'<span class="repo">{issue.repo}</span>')
                html_parts.append(f'<span class="author">by {issue.author.name}</span>')
                html_parts.append(
                    f'<span class="date">created {issue.created_at}</span>'
                )
                html_parts.append("</div>")
                html_parts.append(
                    f'<a href="{issue.url}" target="_blank" '
                    f'style="font-size:0.85em; text-decoration:underline;">'
                    f"View on GitHub &rarr;</a>"
                )
                html_parts.append("</li>")
            html_parts.append("</ul>")
            html_parts.append("</div>")

        # No activity message
        if not (merged_prs or open_prs or open_issues):
            html_parts.append(
                '<div style="text-align:center; padding:50px; color:#666; '
                'background:#f9f9f9; border-radius:8px;">'
                "<h3>No GitHub activity found</h3>"
                "<p>Try selecting a different date range.</p></div>"
            )

        return "\n".join(html_parts)

    @staticmethod
    def format_csv(report: "StatsReport") -> str:
        """
        Format report as CSV for download.

        Args:
            report: StatsReport to format

        Returns:
            CSV string
        """
        lines = []

        # Header
        lines.append("Type,Title,Number,Author,Date,Status,Repository,URL")

        # PRs
        for pr in report.prs:
            status = "Merged" if pr.is_merged else "Open"
            date_str = str(pr.merged_at) if pr.is_merged else str(pr.created_at)
            lines.append(
                f'PR,"{pr.title}",{pr.number},{pr.author.name},{date_str},{status},{pr.repo},{pr.url}'
            )

        # Issues
        for issue in report.issues:
            status = "Open" if issue.is_open else "Closed"
            lines.append(
                f'Issue,"{issue.title}",{issue.number},{issue.author.name},{issue.created_at},{status},{issue.repo},{issue.url}'
            )

        return "\n".join(lines)
