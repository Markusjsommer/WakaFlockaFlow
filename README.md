# WakaFlakaFlow — Automated Cell Population Identification

A no-code, self-hosted flow-cytometry tool. Point it at an FCS file and it
transforms the data, runs **FlowSOM** clustering with a **UMAP** embedding, and
returns **named cell populations** with counts, percentages, and median-marker
tables — then lets you rename populations and export a reproducibility bundle.

This is a real analysis tool, not a demo. It runs entirely on your own machine.
`git clone` → `docker compose up` → open a browser → analyze your FCS files.

---

## Quick start (one command)

You need [Docker](https://docs.docker.com/get-docker/) with Compose v2.

```bash
git clone <this-repo-url> wakaflakaflow
cd wakaflakaflow

# Put your FCS files where the tool can see them:
mkdir -p fcs
cp /path/to/your/*.fcs ./fcs/

# Build and run (first build downloads deps; subsequent runs are instant):
docker compose up --build
```

Then open **<http://localhost:8000>**.

Any `*.fcs` file you drop into `./fcs/` is auto-registered on startup and appears
in the file selector. Your source files are mounted read-only and are never
modified. Runtime state (SQLite provenance DB, exports) lands in `./data/`.

No FCS files present yet? Use the **Load demo** button in the UI to run the exact
same pipeline on locally-available sample data.

---

## The workflow

1. **Pick a file** (or *Load demo*).
2. **Choose your marker panel** — a checkbox list built from the file's channels.
   Scatter (FSC/SSC) and Time are excluded from clustering by default;
   fluorophore markers are pre-checked. Use *all / none* to toggle quickly.
3. **Pick a metacluster count** — preset buttons for 5 / 10 / 15 / 20 / 25
   (default 10).
4. **Run.** The backend arcsinh-transforms the events, runs FlowSOM
   (self-organizing map + metaclustering), and computes a UMAP embedding.
   Progress streams into a progress bar (Loading → Clustering → UMAP → Done).
5. **Explore the results:**
   - a **UMAP scatter** colored by population, with a population legend;
   - a **population table** — color swatch, editable name, metacluster id, cell
     count, percentage of total, and the top median markers per population.
     Rename a population inline; hover a row to highlight its cells on the UMAP.
6. **Export results (.zip)** — a reproducibility bundle containing
   `populations.csv`, `umap_coordinates.csv`, `panel.csv`, a `session_info.txt`
   with tool + engine versions and run parameters, and a provenance README.

---

## Privacy

**No data is uploaded anywhere.** The application, the analysis engines, and the
database all run inside your local container. Your FCS files, the derived
populations, and every export stay on your machine. There is no telemetry, no
account, and no outbound network call during analysis.

---

## Local development

Prefer running the pieces directly? You need Python 3.12+ and Node 20+.

**Backend** — FastAPI + SQLite, served on port **8001**:

```bash
python3 -m venv .venv
./.venv/bin/pip install -r backend/requirements.txt
./.venv/bin/python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8001
```

**Frontend** — Vite dev server on port **5173**, proxying `/api` → `:8001`:

```bash
npm --prefix frontend install
npm --prefix frontend run dev
```

Open <http://localhost:5173>. In the Docker image the SPA is pre-built and served
by the backend itself, so production runs on a single port (**8000**).

To register FCS files in dev, set `WAKAFLAKA_FCS_DIR` to a directory of `*.fcs`
before launching uvicorn (they are registered on the default session at startup).

---

## Architecture

```
Browser (React + Plotly)
        │  /api/v1  (same origin in Docker; proxied in dev)
        ▼
FastAPI + SQLite ── ThreadPoolExecutor
        │  FlowKit (FCS I/O + arcsinh)
        │  FlowSOM (clustering + metaclustering)
        │  umap-learn (2-D embedding)
        ▼
Named populations · median-marker tables · reproducibility export (.zip)
```

The Docker image is a single stage-built artifact: the Vite frontend is compiled
to static assets and served by the same FastAPI process that exposes the API.

---

## License

WakaFlakaFlow is licensed under the **GNU Affero General Public License v3.0**
(AGPL-3.0-or-later). See [`LICENSE`](LICENSE) for the full text and
[`NOTICE.md`](NOTICE.md) for the wrapped engines and their individual licenses.

If you run a modified version of this software as a network service, the AGPL
requires you to offer the corresponding source of your modified version to that
service's users.

### A note on bundled data

The 40-color reference acquisition used during development (phitonex "E1") is
**CC BY-ND** and is therefore **not redistributed** with this project — it is
git-ignored and kept local. Bring your own FCS files; see *Quick start* above.
