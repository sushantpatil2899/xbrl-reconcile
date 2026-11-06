# The API, with the data inside it.
#
# The published marts are about 1.4 MB and change once a day, so they are baked into
# the image rather than fetched at boot. That makes a cold start a local file open,
# which costs the same whether the host bills by the hour or by the request, and it
# means the running container needs no credentials and no network at all to answer.
# Point MARTS_PATH at a mounted directory instead if you would rather have freshness
# than a fast cold start.
#
# Two stages so the bucket credentials never reach the published image. They arrive as
# build secrets, which are mounted for one RUN and leave nothing in a layer, rather
# than as build arguments, which are recorded in the image history for anyone who
# pulls it.
#
# The bucket name and its endpoint travel as build arguments instead, and that is not
# an inconsistency. They are not secrets: both are repository variables rather than
# repository secrets, and neither grants access to anything on its own. Being recorded
# in the image history costs nothing, and the storage factory requires both outright,
# with no default to fall back on.

FROM python:3.13-slim AS marts

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /build
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --locked --no-dev

ARG B2_BUCKET
ARG B2_ENDPOINT

# Declared immediately before the fetch so its value is part of that layer's cache key
# and nothing above it. Without this the fetch below would be served from cache on
# every build after the first, because none of its other inputs change from one day to
# the next, and the image would quietly ship whichever marts the first build happened
# to see. Passing the run id makes the data layer rebuild every time while the
# dependency install above stays cached, which is the expensive half.
ARG MARTS_REVISION

# The only step that touches the bucket. Secrets are mounted here and nowhere else.
# xbrl-fetch-marts verifies every file's size and row count against the published
# index, so a truncated download fails the build rather than shipping short answers.
RUN --mount=type=secret,id=b2_key_id \
    --mount=type=secret,id=b2_key \
    B2_INGEST_KEY_ID="$(cat /run/secrets/b2_key_id)" \
    B2_INGEST_KEY="$(cat /run/secrets/b2_key)" \
    B2_BUCKET="$B2_BUCKET" \
    B2_ENDPOINT="$B2_ENDPOINT" \
    STORAGE_BACKEND=b2 \
    MARTS_PATH=/marts \
    uv run xbrl-fetch-marts


FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Not root. The process reads files and opens a port; it needs nothing else.
RUN useradd --create-home --uid 10001 api
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --locked --no-dev

COPY --from=marts /marts /app/marts

USER api

ENV MARTS_PATH=/app/marts \
    PORT=8000 \
    RATE_PER_SECOND=1 \
    RATE_BURST=60 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# --host 0.0.0.0 because the default of 127.0.0.1 accepts connections only from inside
# the container, so the host's health check never arrives and the container is killed
# as unhealthy.
#
# Proxy headers are deliberately not configured here, because the right setting
# depends on where this runs and getting it wrong is quiet rather than loud:
#
#   uvicorn trusts X-Forwarded-For by DEFAULT, but only from the addresses in
#   forwarded_allow_ips, which defaults to 127.0.0.1. uvicorn reads that from the
#   FORWARDED_ALLOW_IPS environment variable, so set it at deploy time.
#
#   Behind a load balancer, set FORWARDED_ALLOW_IPS to the proxy's own address.
#   Leave it unset and every caller looks like the proxy, so the rate limiter puts
#   the whole world in one bucket and throttles everyone together.
#
#   Do not set it to "*" unless nothing but that proxy can reach this port. "*" trusts
#   the header from whoever sent it, so any caller can forge an address and the
#   limiter stops limiting. Prefer --no-proxy-headers when nothing is in front.
CMD ["sh", "-c", "uv run uvicorn xbrl_reconcile.api.asgi:app --host 0.0.0.0 --port ${PORT}"]
