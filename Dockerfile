# Portfolio Analyst Agent image. One image, two roles, selected by env:
#
#   Web service    RUN_SCHEDULERS=0  UVICORN_WORKERS=N  REDIS_URL=redis://…
#   Worker service RUN_SCHEDULERS=1  UVICORN_WORKERS=1  (exactly ONE instance)
#
# The digest/macro/news schedulers are in-process APScheduler jobs: a second
# scheduler-running process would fire the digest twice and collide on the
# `digests.digest_date` unique constraint — so the worker role must stay at
# one instance with one uvicorn worker. The web role can scale workers only
# with RUN_SCHEDULERS=0, and needs REDIS_URL beyond one worker so the
# snapshot cache is shared. Defaults (no env set) reproduce the original
# single-service topology: schedulers on, one worker.
# See docs/DEPLOY.md "Topology".

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Install dependencies from the hash-pinned lockfile first, for reproducible
# builds and better layer caching. requirements.txt is generated from
# pyproject.toml (see docs/DEPLOY.md "Dependencies & the lockfile"); regenerate
# it whenever pyproject deps change. --require-hashes (auto-enabled since every
# entry is hashed) makes the build fail closed rather than silently pulling a
# newer release — this is what a stray SnapTrade SDK 12.0.0 upgrade would have
# hit instead of reaching prod.
COPY requirements.txt ./
RUN pip install --require-hashes -r requirements.txt

# Then the app package itself, with no dependency resolution (all deps are
# already pinned-installed above).
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-deps .

# Scripts are run by path (migrate.py, sync_wealthsimple.py), not imported.
COPY scripts ./scripts

EXPOSE 8000

# Apply migrations, then serve. Worker count via UVICORN_WORKERS — see the
# role note above before raising it.
CMD ["sh", "-c", "python scripts/migrate.py && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${UVICORN_WORKERS:-1}"]
