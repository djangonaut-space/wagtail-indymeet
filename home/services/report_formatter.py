"""
Report formatting for GitHub stats.

Formats StatsReport data into HTML for admin display.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .github_stats import StatsReport


class ReportFormatter:
    """Formats GitHub stats reports for admin display."""

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
            f'<div class="stat"><span>Closed PRs</span>'
            f"<strong>{report.count_closed_prs()}</strong></div>"
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
                f'<div class="authors-row"><strong>Djangonauts:</strong> '
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

        # Closed PRs
        closed_prs = report.get_closed_prs()
        if closed_prs:
            html_parts.append('<div class="closed-prs">')
            html_parts.append("<h3>🚧 Closed Pull Requests</h3>")
            html_parts.append("<ul>")
            for pr in closed_prs:
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
        if not (merged_prs or closed_prs or open_prs or open_issues):
            html_parts.append(
                '<div class="no-activity">'
                "<h3>No GitHub activity found</h3>"
                "<p>Try selecting a different date range.</p></div>"
            )

        return "\n".join(html_parts)
