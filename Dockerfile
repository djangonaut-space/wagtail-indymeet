FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ARG NODE_MAJOR=20

RUN apt-get update \
  && apt-get install -y ca-certificates curl gnupg \
  && mkdir -p /etc/apt/keyrings \
  && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
  && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
  && apt-get update \
  && apt-get install nodejs -y \
  && rm -rf /var/lib/apt/lists/* /usr/share/doc /usr/share/man \
  && apt-get clean

# Copy the project into the image
ADD . /app

# Sync the project into a new environment, asserting the lockfile is up to date
WORKDIR /app

# Install dependencies
RUN uv sync --locked  --extra dev --extra test

ENV PATH="/home/python/.local/bin:${PATH}" \
    DEBUG="${DEBUG}" \
    PYTHONUNBUFFERED="true" \
    DJANGO_SETTINGS_MODULE="indymeet.settings.dev"


RUN npm install ./theme/static_src

RUN uv run python manage.py tailwind install
RUN uv run python manage.py tailwind build
RUN uv run python manage.py collectstatic --no-input;

CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]
