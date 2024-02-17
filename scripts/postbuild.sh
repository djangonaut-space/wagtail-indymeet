python manage.py tailwind install
python manage.py tailwind build
python manage.py collectstatic --noinput
# Install supervisor
apt-get update -y
apt-get install -y supervisor
# Test what happens when we try to create a sample file
touch test.txt
