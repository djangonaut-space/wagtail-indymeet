"""Tests for the certificate of completion PDF."""

import datetime

from django.test import TestCase

from accounts.factories import UserFactory
from home.certificates import (
    certificate_filename,
    certificate_name,
    generate_certificate_pdf,
)

END_DATE = datetime.date(2026, 11, 23)


class CertificateTests(TestCase):
    def test_name(self):
        user = UserFactory.build(first_name="Grace", last_name="Hopper")
        self.assertEqual(certificate_name(user), "Grace Hopper")

    def test_name_falls_back_to_username(self):
        user = UserFactory.build(first_name="", last_name="", username="ghopper")
        self.assertEqual(certificate_name(user), "ghopper")

    def test_filename(self):
        """Punctuation and spaces are dropped so the name is safe on any filesystem."""
        self.assertEqual(
            certificate_filename("Grace O'Hopper-Fernández", END_DATE),
            "DjangonautSpaceCertificate_GraceOHopperFernández_20261123.pdf",
        )

    def test_pdf(self):
        """WeasyPrint warns about any CSS, font or image it can't use, so expect none."""
        with self.assertNoLogs("weasyprint", level="WARNING"):
            pdf = generate_certificate_pdf("Grace Hopper", END_DATE)
        self.assertTrue(pdf.startswith(b"%PDF"))
