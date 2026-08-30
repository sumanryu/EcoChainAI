# ==============================================================================
# Dockerfile — builds ONE image, used for BOTH the dashboard and the agents.
#
# Why one image for two different things? The dashboard and the agents run
# the exact same Python codebase (src/), just with a different command at
# startup. Building two separate images would mean duplicating everything
# and keeping them in sync. docker-compose.yml decides which COMMAND each
# service runs — same image, different jobs.
# ==============================================================================

# --- Step 1: start from a base image ---
# python:3.9-slim = a minimal Debian Linux with Python 3.9 already installed.
# "slim" = stripped down (no compilers, no docs, etc.) to keep the image
# small — smaller image = faster to build, push, and pull.
FROM python:3.9-slim

# --- Step 2: set the working directory INSIDE the container ---
# Every command after this (COPY, RUN, CMD) happens relative to /app.
# This is a folder inside the container's filesystem, unrelated to any
# folder on your actual laptop.
WORKDIR /app

# --- Step 3: install OS-level dependencies ---
# curl is needed for the health check later; build-essential for anything
# that needs to compile (some pip packages do under the hood).
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*
# "rm -rf /var/lib/apt/lists/*" cleans up apt's cache in the SAME layer —
# doing it in a separate RUN would still leave the cache bloating an earlier
# layer, since Docker layers are additive (deleting in a later layer doesn't
# shrink an earlier one).

# --- Step 4: copy ONLY requirements.txt first, then install ---
# This is the layer-caching trick mentioned above. Docker checks: "did this
# file change since the last build?" If requirements.txt is unchanged,
# Docker reuses the cached "pip install" layer instead of redoing it —
# even if your actual application code changed. Big time saver on rebuilds.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- Step 5: NOW copy the rest of the application code ---
# This happens AFTER pip install specifically so that changing a .py file
# doesn't invalidate the (slow) pip install layer above.
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY infra/ ./infra/
COPY pyproject.toml* ./

RUN chmod +x scripts/entrypoint.sh

# --- Step 6: make src/ importable without PYTHONPATH gymnastics ---
# Same "from src import config" issue we hit locally with Streamlit — fix
# it once, here, for every command that runs in this image.
ENV PYTHONPATH=/app

# --- Step 7: document which port this container listens on ---
# EXPOSE is informational — it does NOT actually publish the port. The real
# port mapping happens in docker-compose.yml (or `docker run -p`). This
# line just documents "this image expects to serve on 8501" for anyone
# reading the Dockerfile.
EXPOSE 8501

# --- Step 8b: entrypoint runs FIRST, always ---
# Wraps whatever CMD is (dashboard or agents) with the S3 data fetch.
ENTRYPOINT ["scripts/entrypoint.sh"]

# --- Step 9: default command ---
# This runs if no other command is specified. docker-compose.yml will
# OVERRIDE this for the agent service (to run agents instead of the
# dashboard) — CMD is a default, not a hard rule.
CMD ["streamlit", "run", "src/dashboard/app.py", "--server.address=0.0.0.0", "--server.port=8501"]
# --server.address=0.0.0.0 matters: Streamlit defaults to listening only on
# localhost INSIDE the container, which would make it unreachable from
# outside even with the port mapped. 0.0.0.0 means "listen on all network
# interfaces," which is what lets the port mapping actually work.
