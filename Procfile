web: uv run gunicorn indymeet.wsgi
worker: uv run python manage.py db_worker --interval 5
scheduler: uv run python manage.py crontask --no-heartbeat
release: scripts/release.sh
