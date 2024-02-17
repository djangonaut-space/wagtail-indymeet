python manage.py tailwind install
python manage.py tailwind build
python manage.py collectstatic --noinput
if [ -z "$DATABASE_URL" ]; then
    echo "Missing DATABASE_URL, migrations will not be run."
elif
    python manage.py migrate
fi
