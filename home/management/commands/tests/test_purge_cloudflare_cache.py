import json
from io import StringIO

import pytest
import requests
import responses as rsps
from django.core import management
from django.core.management import CommandError
from django.test import TestCase, override_settings

PURGE_URL = "https://api.cloudflare.com/client/v4/zones/test-zone-id/purge_cache"


@pytest.fixture(autouse=True)
def cloudflare_settings(settings):
    """Configure Cloudflare credentials for every test in this module.

    test_skips_purge_when_not_configured opts out via override_settings.
    """
    settings.CLOUDFLARE_BEARER_TOKEN = "test-token"
    settings.CLOUDFLARE_ZONE_ID = "test-zone-id"


class PurgeCloudflareCacheCommandTests(TestCase):
    @rsps.activate
    def test_purges_cache_when_configured(self):
        rsps.add(rsps.POST, PURGE_URL, json={"success": True})

        out = StringIO()
        management.call_command("purge_cloudflare_cache", stdout=out)

        self.assertIn("Purged the entire Cloudflare cache.", out.getvalue())
        request = rsps.calls[0].request
        self.assertEqual(json.loads(request.body), {"purge_everything": True})
        self.assertEqual(request.headers["Authorization"], "Bearer test-token")
        self.assertEqual(request.headers["Content-Type"], "application/json")

    @rsps.activate
    def test_raises_when_cloudflare_rejects_purge(self):
        rsps.add(
            rsps.POST,
            PURGE_URL,
            json={"success": False, "errors": [{"message": "invalid zone"}]},
        )

        out = StringIO()
        with self.assertRaisesMessage(CommandError, "invalid zone"):
            management.call_command("purge_cloudflare_cache", stdout=out)

        self.assertNotIn("Purged the entire Cloudflare cache.", out.getvalue())

    @rsps.activate
    def test_raises_on_request_exception(self):
        rsps.add(rsps.POST, PURGE_URL, body=requests.exceptions.ConnectionError("boom"))

        with self.assertRaisesMessage(CommandError, "boom"):
            management.call_command("purge_cloudflare_cache", stdout=StringIO())

    @rsps.activate
    def test_logs_request_exception_for_sentry(self):
        rsps.add(rsps.POST, PURGE_URL, body=requests.exceptions.ConnectionError("boom"))

        with self.assertLogs(
            "home.management.commands.purge_cloudflare_cache", level="ERROR"
        ) as logs:
            with self.assertRaises(CommandError):
                management.call_command("purge_cloudflare_cache", stdout=StringIO())

        self.assertTrue(any(record.exc_info is not None for record in logs.records))

    @override_settings(CLOUDFLARE_BEARER_TOKEN=None, CLOUDFLARE_ZONE_ID=None)
    @rsps.activate
    def test_skips_purge_when_not_configured(self):
        out = StringIO()
        management.call_command("purge_cloudflare_cache", stdout=out)

        self.assertEqual(len(rsps.calls), 0)
        self.assertIn("skipping Cloudflare cache purge", out.getvalue())
