#!/usr/bin/env bash
# Build the wakaflockaflow wheel: compile the SPA and vendor the demo data into
# the package, then build sdist+wheel. The two vendored dirs (backend/webui,
# backend/sample_data) are build artifacts (git-ignored); the wheel is
# self-contained so `pip install wakaflockaflow` needs no separate assets.
set -euo pipefail
cd "$(dirname "$0")/.."

echo ">> building frontend"
npm --prefix frontend install --no-audit --no-fund >/dev/null 2>&1 || npm --prefix frontend install
npm --prefix frontend run build

echo ">> vendoring SPA + demo data into the package"
rm -rf backend/webui backend/sample_data
cp -r frontend/dist backend/webui
cp -r sample_data backend/sample_data

echo ">> building sdist + wheel"
python -m pip install --quiet --upgrade build
python -m build

echo ">> done. Artifacts in dist/:"
ls -1 dist/*.whl dist/*.tar.gz 2>/dev/null || true
