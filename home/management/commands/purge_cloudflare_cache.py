"""
Management command to purge the entire Cloudflare cache.

Wagtail's frontend cache invalidation (``WAGTAILFRONTENDCACHE``) only purges
individual page URLs when their content changes in the CMS, and Wagtail's
``CloudflareBackend`` only exposes purging specific URLs. It does not clear
cached static assets (for example the Tailwind CSS bundle) that are rebuilt on
every deployment, so a release can leave stale styles served from Cloudflare's
edge. This command calls Cloudflare's "purge everything" API directly so
freshly built assets are picked up once a release goes live.
"""

import requests
from django.conf import settings
from django.core.management import BaseCommand

CLOUDFLARE_PURGE_CACHE_URL = (
    "https://api.cloudflare.com/client/v4/zones/{zone_id}/purge_cache"
)


class Command(BaseCommand):
    help = "Purge the entire Cloudflare cache (used after a deployment goes live)."

    def handle(self, *args, **options) -> None:
        bearer_token = getattr(settings, "CLOUDFLARE_BEARER_TOKEN", None)
        zone_id = getattr(settings, "CLOUDFLARE_ZONE_ID", None)

        if not bearer_token or not zone_id:
            self.stdout.write(
                self.style.WARNING(
                    "CLOUDFLARE_BEARER_TOKEN / CLOUDFLARE_ZONE_ID are not configured; "
                    "skipping Cloudflare cache purge."
                )
            )
            return

        try:
            response = requests.post(
                CLOUDFLARE_PURGE_CACHE_URL.format(zone_id=zone_id),
                json={"purge_everything": True},
                headers={
                    "Authorization": f"Bearer {bearer_token}",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            response_json = response.json()
        except (requests.exceptions.RequestException, ValueError) as exc:
            # A failed purge shouldn't fail the deployment - stale cache is
            # recoverable, an aborted release is not.
            self.stderr.write(
                self.style.ERROR(f"Failed to purge Cloudflare cache: {exc}")
            )
            return

        if not response.ok or not response_json.get("success"):
            self.stderr.write(
                self.style.ERROR(f"Failed to purge Cloudflare cache: {response_json}")
            )
            return

        self.stdout.write(self.style.SUCCESS("Purged the entire Cloudflare cache."))
