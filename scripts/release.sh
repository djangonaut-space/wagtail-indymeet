if [ -z "$DATABASE_URL" ]; then
    echo "Missing DATABASE_URL, migrations will not be run."
else
    uv run python manage.py migrate
    uv run python manage.py setup_session_organizers_group
fi
