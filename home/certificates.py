"""Certificates of completion attached to a session's final email.

The certificate is an HTML template rendered to PDF with WeasyPrint, which
avoids running a browser on the worker. The template and its assets are
written for WeasyPrint's CSS support, so preview the PDF after changing them.
"""

import datetime
from pathlib import Path

from django.template.loader import render_to_string
from weasyprint import HTML

from accounts.models import CustomUser

# Fonts and images the template references with relative URLs.
CERTIFICATE_ASSETS_DIR = Path(__file__).resolve().parent / "static" / "certificates"


def certificate_name(user: CustomUser) -> str:
    """The name printed on a user's certificate."""
    return user.get_full_name() or user.username


def certificate_filename(name: str, date: datetime.date) -> str:
    """A filesystem-safe PDF filename, e.g. DjangonautSpaceCertificate_GraceHopper_20261123.pdf."""
    parts = ["DjangonautSpaceCertificate", name.strip(), date.isoformat()]
    stem = "".join(char for char in "_".join(parts) if char.isalnum() or char == "_")
    return f"{stem}.pdf"


def generate_certificate_pdf(name: str, date: datetime.date) -> bytes:
    """Render the certificate of completion as PDF bytes."""
    html = render_to_string(
        "certificates/certificate.html", {"name": name, "date": date}
    )
    return HTML(string=html, base_url=str(CERTIFICATE_ASSETS_DIR)).write_pdf()
