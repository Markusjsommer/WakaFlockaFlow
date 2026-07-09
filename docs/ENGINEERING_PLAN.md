# WakaFlakaFlow — Prototype Engineering Plan (1-day)

*Derived from `WakaFlakaFlow_PRD_v2.md`, `spectral_gating_proposal.md`,
`gating_automation_landscape.md`, `DATASET_COMPARISON.md`.*

**Locked decisions (2026-07-09):**
- Demo = **synthetic batch-correction** (inject a known batch effect into the one real
  file, then correct it and show the effect collapse).
- Correction engine = **real CytoNorm in R, run via Docker** (Bioconductor image).
- Break-glass fallback = **Python pyComBat** if the R/CytoNorm setup misses its time-box.

---

## 0. Reality check (read first)

### The data honesty problem — non-negotiable framing
The only real data on hand is a **single acquisition**: `PBMC_40color_E1_UNMIXED.fcs`
(132,360 events × 47 channels = 40 markers + scatter, Cytek Aurora U0363, 28-Feb-2020) and
its raw/mixed twin. One sample, one batch, one instrument, one day. Real CytoNorm cannot
run on one batch — there is no batch axis to normalize.

So the demo **injects a synthetic batch effect** into this file and shows CytoNorm removing
it. This is a legitimate, standard way to *validate a normalization pipeline* (recover a
known injected drift), and it exercises the entire real stack (FlowKit I/O → R/CytoNorm →
EMD diagnostics). **It is NOT a real multi-batch biological result.** Every screen and the
export report must carry a banner:

> ⚠ SYNTHETIC BATCH EFFECT — drift was injected artificially into a single acquisition to
> validate the CytoNorm pipeline. This is a mechanism/plumbing demo, not real multi-batch data.

Do not let anyone present this as a real cohort result. The real batch-robustness
demonstration (proposal demo #3) needs a genuine multi-day/multi-instrument dataset — a
Phase-2 data-acquisition task, not tomorrow.

### License note
Phitonex E1 is **CC BY-ND**. We create *derived* FCS (drifted + corrected). Fine as
internal input; **do not commit derived/modified FCS into the public repo.** Keep all
generated FCS under gitignored `data/`. Flag for counsel before any repo publish.

### What we deliberately drop for day 1
Celery/Redis, Postgres, auth/multi-user, the interactive gate editor, PeacoQC, diffcyt,
openCyto template gating, WebGL million-event rendering, Tauri. All map to PRD Phase 2/3
(§9). We keep exactly what the batch-correction story needs.

---

## 1. Demo definition — the vertical slice that must work tomorrow

```
Load UNMIXED fcs → transform → SYNTHETIC SPLIT into pseudo-batches + shared control
  → INJECT known per-marker drift into batch(es)
  → CytoNorm.train on controls (R, Docker) → CytoNorm.normalize all samples
  → EMD per marker: before vs after  →  UMAP colored by batch: before vs after
  → browser: before/after density overlays + EMD table + UMAP pair + synthetic banner
  → export: corrected FCS + emd_stats.csv + injected-drift params + plots
```

**"Working" = ** on the real E1 file, the app injects drift (EMD between batches jumps),
runs real CytoNorm, and the after-EMD collapses toward zero, shown as a before/after plot
and a numeric mean-EMD-reduction % (mirror the paper's ~61%). Start-to-finish in the
browser, one click.

---

## 2. Synthetic batch design (the scientific crux — get this right)

**Split.** Randomly partition the 132,360 events into 2 pseudo-batches, A and B (random →
identical underlying biology, so any post-split difference is purely the injected effect).
Start with 2 batches; 3 is a stretch goal for a richer plot.

**Shared control (CytoNorm requires per-batch controls).** Draw one random ~20k-event
aliquot = the "control." Copy it into every batch, then apply that batch's drift to its
copy. This is exactly CytoNorm's model: aliquots of one control run in every batch. The
non-control remainder of each batch = the "validation samples" that get normalized.

**Inject drift.** On ~6–10 of the 40 markers, apply a batch-specific **monotone** warp to
batch B (and identity, or a different warp, to A):
`x' = a·x + b` per marker, or a gentle monotone quantile squash. Monotone so CytoNorm's
monotone-Hermite spline can fairly recover it. Record `(marker, a, b)` → these injected
params go into the export so the recovery is auditable.

**Transform.** arcsinh, cofactor ≈ 150 for fluorescence spectral (PRD Layer 3: 150–500 for
fluorescence FC; 5 is CyTOF-only). Normalize on transformed values; keep it tunable.

**Metric.** Per-marker Earth Mover's Distance (`scipy.stats.wasserstein_distance`) between
batch A and batch B distributions, computed **before** (post-injection) and **after**
(post-CytoNorm). Report per-marker + mean. Expect mean EMD to drop sharply. Also UMAP
(subsample ≤30k) colored by batch: two clouds before → overlapping after.

All of §2 is **Python** (FlowKit + numpy + scipy + umap). R does exactly one thing:
CytoNorm train+apply. Smallest possible R surface = lowest 1-day risk.

---

## 3. Architecture

```
┌──────────────────────────────────────────────────────────┐
│  React + Vite SPA (single page)                           │
│  synthetic-banner · run button · progress · before/after   │
│  density plots (Plotly) · EMD table · UMAP before/after    │
└───────────────▲──────────────────────┬────────────────────┘
                │ REST + 2s poll        │
┌───────────────┴──────────────────────▼─────────────────────┐
│  FastAPI (uvicorn), single process, ThreadPoolExecutor job  │
│  Python does everything except the correction:              │
│   FlowKit (FCS load/write) · numpy (split+drift)            │
│   scipy (EMD) · umap-learn (embed) · pandas/pyarrow         │
│         ────────── file-based IPC ──────────                │
│   data/jobs/{id}/input/*.fcs + params.json                  │
│         ↓  docker run  ↑                                     │
│   ┌─────────────────────────────────────────────┐          │
│   │  Docker: bioconductor image + CytoNorm       │          │
│   │  run_cytonorm.R: flowCore→CytoNorm.train→    │          │
│   │  normalize → output/corrected_*.fcs          │          │
│   └─────────────────────────────────────────────┘          │
│  SQLite (Job/run rows) · storage: ./data/                   │
└─────────────────────────────────────────────────────────────┘
```

This is a **minimal instance of the PRD §2.5 Python↔R IPC** (job dir, `params.json`,
`error.json`), scoped to one job type. Exchange format is **FCS**, not parquet — flowCore
reads FCS natively and CytoNorm operates on flowSet/flowFrame, so no `arrow`-in-R
dependency. Python writes batch + control FCS in; R writes corrected FCS out.

---

## 4. Tech stack (pinned)

Backend `requirements.txt`:
```
fastapi>=0.111
uvicorn[standard]>=0.30
flowkit==1.3.2            # FCS read/write, confirmed on PyPI, no R
numpy>=2.0
scipy>=1.11               # wasserstein_distance (EMD)
umap-learn>=0.5
pandas>=2.0
pyarrow>=14.0
scikit-learn>=1.4
sqlalchemy>=2.0
pydantic>=2.0
python-multipart
combat>=0.3.3             # pyComBat — BREAK-GLASS fallback only
```
R (inside Docker only):
```
FROM bioconductor/bioconductor_docker:RELEASE_3_20
flowCore, FlowSOM  (BiocManager)  +  CytoNorm (remotes::install_github saeyslab/CytoNorm)
```
Frontend: node ≥20 (have v25) · react 18 + vite 5 · plotly.js-dist-min.
Present: Python 3.13.11, Node v25.9.0, Docker ✓, R ✗ (that's why R lives in Docker).

---

## 5. Repo layout

```
WakaFlakaFlow/
├── backend/
│   ├── main.py               # FastAPI + routes
│   ├── db.py / models.py      # SQLite: Session, FCSFile, Job, BatchCorrectionRun
│   ├── jobs.py                # ThreadPoolExecutor + progress writes
│   ├── analysis/
│   │   ├── io.py             # FlowKit load/write, transform
│   │   ├── synth.py          # split + shared control + inject drift  (§2)
│   │   ├── emd.py            # per-marker wasserstein before/after
│   │   ├── embed.py          # UMAP before/after
│   │   └── cytonorm.py       # writes job dir, docker run, reads output/error
│   ├── r_scripts/run_cytonorm.R
│   ├── docker/Dockerfile.r
│   └── requirements.txt
├── frontend/  (vite react + plotly)
├── data/                      # gitignored: uploads, job dirs, corrected FCS, sqlite
└── README.md
```

---

## 6. Task breakdown (critical path, ~9.5 h + buffer)

**T0 is the long pole — start the Docker build FIRST and let it bake in the background
while you write Python.**

| # | Task | Est | Notes |
|---|------|-----|-------|
| **T0** | Build R image: `docker build -f docker/Dockerfile.r` (flowCore+FlowSOM+CytoNorm). Smoke: `docker run img Rscript -e 'library(CytoNorm)'` | 2–3 h wall (bg) | **Biggest risk.** Kick off immediately. Time-box: if not green by ~hour 3 → break-glass pyComBat. |
| **T1** | Python: FlowKit load UNMIXED, arcsinh transform, round-trip write FCS | 0.75 h | de-risks I/O early |
| **T2** | `synth.py`: split + shared control + inject monotone drift; write batch/control FCS to job dir; sanity-check EMD jumps post-injection | 1.25 h | the scientific core (§2) |
| **T3** | `run_cytonorm.R` + `cytonorm.py`: docker run on the toy FCS → corrected FCS out. **The make-or-break integration.** | 1.5 h | needs T0 green |
| **T4** | `emd.py`: per-marker + mean EMD before vs after; assert after < before | 0.75 h | the money metric |
| **T5** | `embed.py`: UMAP before/after, subsample ≤30k, colored by batch | 0.75 h | |
| **T6** | FastAPI wrap: `POST /batch-correction` → threaded job → progress → `GET` results; `GET /jobs/{id}` poll | 1.25 h | locks 2s poll contract |
| **T7** | React: synthetic banner, run btn, progress bar, before/after density (Plotly, per-marker dropdown), EMD table, UMAP pair | 2 h | biggest FE block |
| **T8** | Export: corrected FCS + emd_stats.csv + injected params + plots → zip; README one-command run | 1 h | |
| **T9** | End-to-end on E1, fix, rehearse demo | 1 h | **reserve — do not skip** |

**Cut order if behind:** drop UMAP (T5) → drop per-marker dropdown, show 4 fixed markers
(T7) → drop zip, download loose files (T8). **Never cut** T2/T3(or fallback)/T4/T9 — that
is the irreducible demo.

**Break-glass (if T0/T3 R path fails by time-box):** swap `cytonorm.py` to call pyComBat
(pure Python, already in requirements). Everything else — split, drift, EMD, UMAP, UI —
is unchanged. The demo still shows before/after collapse; you just say "ComBat" instead of
"CytoNorm" and note CytoNorm-in-R is the Phase-2 engine. This guarantees something ships.

---

## 7. Minimal API + data model

```
POST /api/v1/sessions                              -> {session_id}
POST /api/v1/sessions/{id}/files                   (multipart) -> file meta   (or auto-load E1)
PUT  /api/v1/sessions/{id}/transform
POST /api/v1/sessions/{id}/batch-correction        (synth params) -> {job_id}
GET  /api/v1/sessions/{id}/batch-correction/{rid}  -> emd before/after, umap refs, banner
POST /api/v1/sessions/{id}/export                  -> {job_id}
GET  /api/v1/jobs/{job_id}                          (poll 2s)
```
Tables (4 of PRD's 12): `Session, FCSFile, Job, BatchCorrectionRun` (+ store `emd_before`,
`emd_after`, injected-drift params, paths). PRD field names kept → additive later, no
rewrite.

---

## 8. Risks & mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| **Docker R image build fails / too slow** | No CytoNorm | Start T0 first, run in bg; time-box to hour 3; **pyComBat break-glass** guarantees the demo |
| CytoNorm rejects synthetic control setup | Correction errors | Match its exact model (per-batch control aliquots, monotone drift); test on toy 20k events in T3 before full run |
| Injected drift non-monotone → poor recovery | Weak "after" plot | Keep warps monotone (a·x+b); CytoNorm's spline handles those cleanly |
| Demo read as real batch data | Credibility / scientific integrity | **Mandatory synthetic banner** on every screen + export; say it aloud in the demo |
| FCS write via FlowKit loses keywords | R read fails | Round-trip test in T1 before building on it |
| Frontend eats the day | No UI | Plotly only (no custom WebGL); fallback = matplotlib PNGs served + Swagger |

---

## 9. Deferred → PRD phases

- **Phase 2:** real multi-batch data + real CytoNorm cohort demo (proposal demo #3);
  PeacoQC, diffcyt, openCyto template gating, FlowJo `.wsp` *import*, the interactive gate
  editor, full §2.5 R-IPC for all 5 engines, Celery/Redis.
- **Phase 3:** Docker Compose facility deploy, Tauri desktop, Postgres/multi-user/auth,
  deck.gl million-event WebGL, GatingML round-trip fidelity, in-app unmixing.
- **Pre-public-release blocker:** licensing (CytoNorm GPL, openCyto/CytoML AGPL, phitonex
  data CC BY-ND). Prototype is local/internal → not a tomorrow blocker; settle with counsel
  before any networked release or repo publish of derived data.

---

## 10. Demo script (what to click tomorrow)

1. `docker` R image already built; `uvicorn main:app` + `npm run dev`.
2. Browser loads E1; **synthetic banner visible**.
3. Set injected-drift markers/magnitude (or accept defaults) → Run.
4. Progress bar advances (Python split/drift → docker CytoNorm → EMD/UMAP) → done.
5. Before/after density overlay for a drifted marker: two curves apart → aligned.
6. EMD table: per-marker before vs after; mean reduction % headline.
7. UMAP before (two batch clouds) vs after (overlapped).
8. Export → zip with corrected FCS + emd_stats.csv + injected params.

If 3→8 runs on E1 with EMD visibly collapsing, the prototype is a success.

---

## 11. Immediate next action

Kick off **T0 (Docker R image build)** now — it's the long pole and can bake in the
background while the rest is built. `docker/Dockerfile.r` and `r_scripts/run_cytonorm.R`
skeletons are written alongside this plan.
```
