# Portfolio Analyst Agent — single-process image.
#
# IMPORTANT: run exactly ONE instance of this container with ONE uvicorn worker.
# The morning digest is driven by an in-process APScheduler; a second process
# (extra replica or `--workers >1`) would fire the digest twice and collide on
# the `digests.digest_date` unique constraint. Scale out is a non-goal for this
# single-user app.

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install .

# Scripts are run by path (migrate.py, sync_wealthsimple.py), not imported.
COPY scripts ./scripts

EXPOSE 8000

# Apply migrations, then serve. Single worker — see note above.
CMD ["sh", "-c", "python scripts/migrate.py && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
