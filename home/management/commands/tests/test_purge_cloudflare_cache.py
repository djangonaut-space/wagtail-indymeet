from unittest.mock import patch

import pytest
import requests
from django.core import management
from django.core.management import CommandError
from django.test import override_settings


@pytest.mark.django_db
class TestPurgeCloudflareCacheCommand:
    @override_settings(
        CLOUDFLARE_BEARER_TOKEN="test-token", CLOUDFLARE_ZONE_ID="test-zone-id"
    )
    @patch("home.management.commands.purge_cloudflare_cache.requests.post")
    def test_purges_cache_when_configured(self, mock_post, capsys):
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {"success": True}

        management.call_command("purge_cloudflare_cache")

        mock_post.assert_called_once_with(
            "https://api.cloudflare.com/client/v4/zones/test-zone-id/purge_cache",
            json={"purge_everything": True},
            headers={
                "Authorization": "Bearer test-token",
                "Content-Type": "application/json",
            },
            timeout=30,
        )
        captured = capsys.readouterr()
        assert "Purged the entire Cloudflare cache." in captured.out

    @override_settings(
        CLOUDFLARE_BEARER_TOKEN="test-token", CLOUDFLARE_ZONE_ID="test-zone-id"
    )
    @patch("home.management.commands.purge_cloudflare_cache.requests.post")
    def test_raises_when_cloudflare_rejects_purge(self, mock_post, capsys):
        mock_post.return_value.ok = True
        mock_post.return_value.json.return_value = {
            "success": False,
            "errors": [{"message": "invalid zone"}],
        }

        with pytest.raises(CommandError, match="invalid zone"):
            management.call_command("purge_cloudflare_cache")

        captured = capsys.readouterr()
        assert "Purged the entire Cloudflare cache." not in captured.out

    @override_settings(
        CLOUDFLARE_BEARER_TOKEN="test-token", CLOUDFLARE_ZONE_ID="test-zone-id"
    )
    @patch("home.management.commands.purge_cloudflare_cache.requests.post")
    def test_raises_on_request_exception(self, mock_post):
        mock_post.side_effect = requests.exceptions.ConnectionError("boom")

        with pytest.raises(CommandError, match="boom"):
            management.call_command("purge_cloudflare_cache")

    @override_settings(
        CLOUDFLARE_BEARER_TOKEN="test-token", CLOUDFLARE_ZONE_ID="test-zone-id"
    )
    @patch("home.management.commands.purge_cloudflare_cache.requests.post")
    def test_logs_request_exception_for_sentry(self, mock_post, caplog):
        mock_post.side_effect = requests.exceptions.ConnectionError("boom")

        with pytest.raises(CommandError):
            management.call_command("purge_cloudflare_cache")

        assert any(
            record.levelname == "ERROR" and record.exc_info is not None
            for record in caplog.records
        )

    @override_settings(CLOUDFLARE_BEARER_TOKEN=None, CLOUDFLARE_ZONE_ID=None)
    @patch("home.management.commands.purge_cloudflare_cache.requests.post")
    def test_skips_purge_when_not_configured(self, mock_post, capsys):
        management.call_command("purge_cloudflare_cache")

        mock_post.assert_not_called()
        captured = capsys.readouterr()
        assert "skipping Cloudflare cache purge" in captured.out
