This file contains the commands that were run to configure the Hetzner VPS
server with Dokku to run the application.

It assumes there's a PostgreSQL, ``pg_dump`` generated sql file in backup.sql.
It also assume there's a folder of all media files at media/media.

```bash
dokku postgres:create djangonaut-space
dokku postgres:connect djangonaut-space < backup.sql

dokku config:set djangonaut-space SECRET_KEY='hunter2' \
DJANGO_SETTINGS_MODULE="indymeet.settings.production" \
RECAPTCHA_PRIVATE_KEY="hunter2" \
RECAPTCHA_PUBLIC_KEY="hunter4" \
SENTRY_DSN="hunter5" \
MAILJET_API_KEY="hunter6" \
MAILJET_SECRET_KEY="hunter7" \
BASE_URL="https://djangonaut.space"

chown -R dokku:dokku /var/lib/dokku/data/storage/djangonaut-space/
dokku storage:mount djangonaut-space /var/lib/dokku/data/storage/djangonaut-space/staticfiles:/app/staticfiles
dokku storage:mount djangonaut-space /var/lib/dokku/data/storage/djangonaut-space/mediafiles:/app/mediafiles

dokku storage:ensure-directory djangonaut-space mediafiles
dokku storage:ensure-directory djangonaut-space staticfiles

cp -r media/media/* /var/lib/dokku/data/storage/djangonaut-space/mediafiles/
dokku storage:ensure-directory --chown herokuish djangonaut-space mediafiles

dokku nginx:set djangonaut-space client-max-body-size 15m

# Paste the file from wagtail-indymeet/nginx.conf.d/djangonaut-space-static.conf
sudo -u dokku nano /home/dokku/djangonaut-space/nginx.conf.d/djangonaut-space-static.conf
dokku proxy:build-config djangonaut-space

dokku domains:add djangonaut-space djangonaut.space
dokku letsencrypt:enable djangonaut-space
```
