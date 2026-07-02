if [ -z "$DATABASE_URL" ]; then
    echo "Missing DATABASE_URL, migrations will not be run."
else
    uv run python manage.py migrate
    uv run python manage.py setup_session_organizers_group
fi

# Purge the Cloudflare cache so freshly built static assets (e.g. the Tailwind
# CSS bundle) are served after the release goes live. No-ops when Cloudflare is
# not configured.
uv run python manage.py purge_cloudflare_cache
