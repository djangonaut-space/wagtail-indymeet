web: uv run gunicorn indymeet.wsgi
worker: uv run python manage.py db_worker --interval 5
release: scripts/release.sh
