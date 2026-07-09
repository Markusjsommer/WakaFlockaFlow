# syntax=docker/dockerfile:1
#
# WakaFlakaFlow — single combined image: Python backend + R engines + built SPA.
# The React app is compiled to static assets and served by FastAPI, and the R
# spectral engines (AutoSpectral unmixing; FlowSOM/flowWorkspace) run in-process
# via Rscript. One `docker compose up`, one port, no external services.
#
#   docker build -t wakaflakaflow .
#
# NOTE: this is a large image (Bioconductor + AutoSpectral + scientific Python).
# First build is long; subsequent builds are cached.

# ---------------------------------------------------------------------------
# Stage 1 — build the frontend (Vite + React) into static assets.
# ---------------------------------------------------------------------------
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci || npm install
COPY frontend/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2 — R (Bioconductor) + Python runtime.
# ---------------------------------------------------------------------------
FROM bioconductor/bioconductor_docker:RELEASE_3_20

# --- R spectral engines -----------------------------------------------------
RUN R -e 'BiocManager::install(c("flowCore","FlowSOM","flowWorkspace"), update=FALSE, ask=FALSE)'
RUN R -e 'install.packages(c("remotes","jsonlite"), repos="https://cloud.r-project.org"); \
          remotes::install_github("DrCytometer/AutoSpectral", upgrade="never")'
RUN R -e 'suppressMessages({library(flowCore);library(FlowSOM);library(flowWorkspace);library(AutoSpectral);library(jsonlite)}); \
          cat("R engines OK: AutoSpectral", as.character(packageVersion("AutoSpectral")), "\n")'

# --- Python backend ---------------------------------------------------------
# libgomp1 = OpenMP runtime for numba/umap-learn.
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv $VIRTUAL_ENV
ENV PATH="$VIRTUAL_ENV/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --upgrade pip && pip install -r /app/backend/requirements.txt

# --- Application code + compiled SPA + bundled demo data --------------------
COPY backend/ /app/backend/
COPY sample_data/ /app/sample_data/
COPY --from=frontend /fe/dist /app/static

ENV WAKAFLAKA_STATIC=/app/static \
    WAKAFLAKA_R_MODE=local \
    WAKAFLAKA_R_SCRIPTS=/app/backend/r_scripts

# REPO_ROOT = parent of backend/ = /app  ->  DATA_DIR=/app/data, DEMO_DIR=/app/sample_data/...
WORKDIR /app/backend
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
