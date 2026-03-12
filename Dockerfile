FROM ghcr.io/astral-sh/uv:python3.11-bookworm-slim

ARG NODE_MAJOR=20

ENV PATH="/home/python/.local/bin:${PATH}" \
    PYTHONUNBUFFERED="true" \
    PYTHONDONTWRITEBYTECODE="1" \
    UV_PROJECT_ENVIRONMENT="/opt/venv" \
    UV_LINK_MODE="copy"

RUN --mount=target=/var/lib/apt/lists,type=cache,sharing=locked \
    --mount=target=/var/cache/apt,type=cache,sharing=locked \
    rm -f /etc/apt/apt.conf.d/docker-clean \
    && apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
    && mkdir -p /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_$NODE_MAJOR.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends nodejs libgdal-dev g++ gdal-bin libpq-dev

WORKDIR /app

COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --group test --group dev --locked

# Install npm dependencies before copying the full project so this layer is
# cached as long as package.json and package-lock.json are unchanged.
COPY theme/static_src/package.json theme/static_src/package-lock.json ./theme/static_src/

RUN --mount=type=cache,target=/root/.npm \
    npm install --prefix ./theme/static_src

COPY . /app

RUN uv run python manage.py tailwind build
RUN uv run python manage.py collectstatic --no-input

CMD ["uv", "run", "python", "manage.py", "runserver", "0.0.0.0:8000"]
