FROM ubuntu:20.04
FROM python:3.11-slim-bookworm

WORKDIR /app

ARG NODE_MAJOR=20

RUN apt-get update \
  && apt-get install -y ca-certificates curl gnupg \
  && mkdir -p /etc/apt/keyrings \
  && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
  && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
  && apt-get update \
  && apt-get install nodejs -y \
  && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man \
  && apt-get clean \
  && useradd --create-home python \
  && chown python:python -R /app

USER python

COPY --chown=python:python requirements/requirements.txt ./

RUN pip install -r requirements.txt

ENV DEBUG="${DEBUG}" \
    PYTHONUNBUFFERED="true" \
    PATH="${PATH}:/home/python/.local/bin" \
    DJANGO_SETTINGS_MODULE="indymeet.settings.dev" \
    USER="python"

COPY --chown=python:python . .

WORKDIR /app

RUN npm install ./theme/static_src

RUN python manage.py tailwind install --no-input;
RUN python manage.py tailwind build --no-input;
RUN python manage.py collectstatic --no-input;

CMD ["python", "manage.py", "runserver"]
