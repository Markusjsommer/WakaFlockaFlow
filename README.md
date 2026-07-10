# WakaFlockaFlow, a no-code tool for automated spectral flow cytometry analysis

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![Runs locally](https://img.shields.io/badge/data-stays%20local-brightgreen.svg)](#privacy)

WakaFlockaFlow takes spectral flow cytometry FCS files and, without any coding,
produces named cell populations with counts, frequencies, marker profiles, and
functional-state calls, then compares them across an experimental cohort with a
statistic. It runs a post-acquisition workflow behind a browser interface:
spectral unmixing, transformation, automated population identification with
cell-type annotation (FlowSOM + UMAP), multi-sample cohort analysis on one shared
embedding, differential abundance and state testing, and explainable gating
paths. It exports a reproducibility bundle for every run. Cross-acquisition
batch-correction engines (CytoNorm, ComBat) are included; a guided interface for
them is on the roadmap.

It covers four of the five things a lab asks of post-acquisition analysis:
composition (what cell types, in what proportions), state (what those cells are
doing), quality and harmonization (trustworthy, comparable data), and
differential analysis (what changed between conditions). Rare-event detection
(MRD, antigen-specific cells) is a deliberate later vertical.

> WakaFlockaFlow is a **post-acquisition analysis** tool. It reads the standard
> FCS files your instrument already exports (Cytek Aurora, Sony ID7000, BD
> FACSymphony, and any other ISAC-compliant device). It does not control the
> cytometer, and it does not sort cells; it analyzes what the instrument
> produced.

> The tool is **self-hosted**: the application, the analysis engines, and the
> database all run in a container on your own machine. No FCS file, population,
> or result is ever uploaded. See [Privacy](#privacy).

WakaFlockaFlow orchestrates established, peer-reviewed cytometry engines rather
than reimplementing them. It is designed to slot into an existing workflow: it
reads standard FCS and can round-trip gating definitions with FlowJo, rather
than to replace the tools a lab already uses.

## What it does

WakaFlockaFlow covers the post-acquisition workflow in stages, each usable on its
own:

* **Spectral unmixing**: resolves raw multi-detector signal into
  per-fluorophore channels using single-stain controls, for instruments or
  experiments where only raw (mixed) FCS is available.
* **Transformation**: arcsinh transformation with a per-channel cofactor;
  scatter and time channels are held out of clustering by default.
* **Automated population identification**: FlowSOM self-organizing-map
  clustering with metaclustering, paired with a UMAP embedding for
  visualization. Populations are returned with cell counts, frequencies, and
  per-population median-marker tables, and can be renamed interactively.
* **Automatic cell-type annotation**: a transparent marker-signature engine
  labels each population with a canonical cell type (CD4 T, CD8 T, B, NK,
  monocyte, dendritic-cell and other lineages); labels are editable, and
  populations with no confident match are left unlabelled rather than forced.
* **Functional state**: each population is scored on named functional axes
  (activation, exhaustion, memory, proliferation, cytotoxicity, signaling) from
  its marker medians; an axis is scored only when its markers are in the panel.
* **Cohort analysis**: cluster tens to hundreds of samples together on one
  shared UMAP so populations are directly comparable, quantify each population
  per sample, and highlight any single sample on the shared embedding. Samples
  with different panels are clustered on their common markers.
* **Differential analysis**: test which populations change in abundance and
  which markers shift within a population across experimental groups. Uses
  diffcyt (edgeR + limma) when available, with a dependency-light Python
  rank-test fallback that runs everywhere.
* **Gating paths**: for each population, a short sequence of marker-threshold
  gates (a one-vs-rest decision tree) that reproduces the cluster, reported with
  a reconstruction-quality score and biaxial plots, and exportable to FlowJo as
  real marker gates.
* **Batch correction (engine)**: cross-acquisition normalization engines
  (CytoNorm, with a ComBat fallback) are included and callable; a guided UI
  workflow for multi-batch correction is on the roadmap.
* **Reproducibility export**: every run produces a `.zip` bundle with the
  population table, UMAP coordinates, the marker panel, run parameters, and
  engine versions.
* **FlowJo interoperability**: export an augmented FCS plus a FlowJo workspace
  (`.wsp`) and a GatingML 2.0 file, so the automated populations open in FlowJo
  as named gates defined by their real marker thresholds (from the gating path).

## Installation

WakaFlockaFlow ships as a Docker image and runs with a single command. The only
prerequisite is [Docker](https://docs.docker.com/get-docker/) with Compose v2.

    git clone https://github.com/Markusjsommer/WakaFlockaFlow.git
    cd WakaFlockaFlow
    docker compose up --build

The first build downloads dependencies; subsequent starts are immediate. When
the container is running, open <http://localhost:8000>.

> The build bundles a small permissively-licensed demo dataset, so the tool is
> usable immediately with no data of your own; the demo files are preloaded in
> the file selector, ready to run. See [Data](#bundled-data).

## Usage

### Analyzing your own files

Place `*.fcs` files in a `fcs/` directory before starting the container; they
are registered on startup and appear in the file selector.

    mkdir -p fcs
    cp /path/to/your/*.fcs ./fcs/
    docker compose up

The `fcs/` directory is mounted read-only, source files are never modified.
Runtime state (the SQLite provenance database and exports) is written to
`data/`.

### Identifying populations

1. Select a file (the bundled demo is preloaded in the selector).
2. Choose the marker panel. The panel is built from the file's channels;
   fluorophore markers are pre-selected and scatter/time channels are excluded
   from clustering by default.
3. Choose a metacluster count (default 10).
4. Run. The backend transforms the events, runs FlowSOM, and computes a UMAP
   embedding, streaming progress through the interface.
5. Inspect results: a UMAP scatter colored by population, and a population table
   with counts, frequencies, and top median markers. Each population is
   automatically labelled with a cell type where the panel's markers support one
   (see below). Rename populations inline; hovering a table row highlights that
   population on the embedding.
6. Export the reproducibility bundle (`.zip`).

### Cell-type annotation

After clustering, each population is labelled with a canonical cell type by a
transparent marker-signature engine: it z-scores each marker's median across
populations and matches the high/low profile against known lineage signatures
(CD4/CD8 T-cell subsets, B, NK, monocytes, dendritic cells, and more).
Annotation requires **marker names**: files whose FCS carries them (including the
bundled demo) are labelled out of the box. Fluorophore-only files (e.g. `BUV395-A`)
are mapped in a built-in **panel editor**: assign a marker to each channel, with a
bulk-paste option for large panels, after which populations are re-annotated
instantly without re-clustering. All labels are editable.

### Spectral unmixing

For raw (mixed) FCS, provide single-stain control files and start an unmixing
job; the unmixed per-marker output feeds directly into population
identification.

### Batch correction

Cross-acquisition normalization engines (**CytoNorm** by default, with a
pure-Python **ComBat** fallback) are included and callable via the backend to
make samples run on different days or instruments comparable. A guided
multi-batch workflow in the interface is on the roadmap; it is not yet a
point-and-click stage.

## Privacy

WakaFlockaFlow performs no outbound network calls during analysis. There is no
telemetry, no account, and no upload step. FCS files, derived populations, and
exports remain on the machine running the container.

## Bundled data

The repository includes a small, permissively-licensed demo dataset:
**flowSpecs** example spectral data (Artistic-2.0), exported to FCS under
`sample_data/spectral_pbmc/`, preloaded in the file selector so the tool is
usable with no data of your own. See
[`NOTICE.md`](NOTICE.md) for details and provenance.

The 40-color reference acquisition used during development ("phitonex E1") is
licensed CC BY-ND and is therefore **not** redistributed with this project; it
is git-ignored. Bring your own FCS files to analyze data at that scale.

## Development

Running the components directly (outside Docker) requires Python 3.12+ and
Node 20+.

**Backend** (FastAPI + SQLite, port 8001):

    python3 -m venv .venv
    ./.venv/bin/pip install -r backend/requirements.txt
    ./.venv/bin/python -m uvicorn main:app --app-dir backend --host 127.0.0.1 --port 8001

**Frontend** (Vite dev server, port 5173, proxying `/api` to the backend):

    npm --prefix frontend install
    npm --prefix frontend run dev

Then open <http://localhost:5173>. In the Docker image the frontend is
pre-built and served by the backend process, so a production deployment uses a
single port (8000). Set `WAKAFLOCKA_FCS_DIR` to a directory of `*.fcs` files to
register them at startup during development.

The REST API is served under `/api/v1`; interactive documentation is available
at `/docs` (FastAPI/OpenAPI) when the backend is running.

## Architecture

    Browser (React + Plotly)
            │  /api/v1
            ▼
    FastAPI + SQLite  ──  background job workers
            │  FlowKit         FCS I/O, arcsinh transform
            │  FlowSOM         SOM clustering + metaclustering
            │  umap-learn      2-D embedding
            │  scikit-learn    gating-path decision trees
            │  diffcyt / R     differential abundance + state (edgeR + limma)
            │  CytoNorm / R    batch correction (R engines via subprocess)
            ▼
    Named populations · marker tables · reproducibility export (.zip)

The Python core and the R-based engines run as separate processes; the frontend
is compiled to static assets and served by the same FastAPI process in the
Docker image.

## Acknowledgments

WakaFlockaFlow orchestrates several established libraries, each retaining its own
license and copyright. If you use WakaFlockaFlow in published work, please cite
the underlying engines you rely on:

* **FlowKit**: FCS I/O and transforms (White et al., *Front. Immunol.* 2021)
* **FlowSOM**: clustering and metaclustering (Van Gassen et al., *Cytometry A*
  2015)
* **UMAP**: dimensionality reduction (McInnes et al., 2018)
* **diffcyt / edgeR / limma**: differential discovery (Weber et al., *Commun.
  Biol.* 2019; Robinson et al. 2010; Ritchie et al. 2015)
* **CytoNorm**: batch normalization (Van Gassen et al., *Cytometry A* 2020)
* **flowCore / openCyto**: R data structures and gating (Hahne et al. 2009;
  Finak et al. 2014)

See [`NOTICE.md`](NOTICE.md) for the complete list of wrapped engines and their
licenses.

## License

WakaFlockaFlow is licensed under the **GNU Affero General Public License v3.0**
(AGPL-3.0-or-later); see [`LICENSE`](LICENSE). If you run a modified version as a
network service, the AGPL requires you to offer the corresponding source of your
modified version to that service's users. The wrapped analysis engines remain
under their own licenses, listed in [`NOTICE.md`](NOTICE.md).
