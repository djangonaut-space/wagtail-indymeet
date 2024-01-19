#!/bin/sh
# Run the local web application

python manage.py tailwind start &
python manage.py runserver
