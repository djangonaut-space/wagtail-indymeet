if [ -z "$DATABASE_URL" ]; then
    echo "Missing DATABASE_URL, migrations will not be run."
else
    python manage.py migrate
fi
