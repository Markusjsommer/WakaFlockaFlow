# A no-code spectral cytometry analysis hub: proposal and engineering spec

*Internal proposal. Part A is a high-level pitch for decision-makers; Part B is an engineering specification for whoever builds it. The two can be circulated separately.*

---

# Part A — Proposal

## The one-paragraph pitch

Our biologists run spectral flow cytometry and are bottlenecked not by the instruments but by the **analysis**: gating is manual, slow, subjective, and does not scale to the 30–50-marker panels spectral machines produce. The best automated methods already exist and outperform manual gating, but they live in R and Python packages that require coding — precisely the barrier our wet-lab scientists hit. We propose to build a **no-code, locally-deployable analysis hub that ingests standard FCS files from any spectral instrument and returns QC, batch-corrected high-dimensional analysis, automated gating, differential statistics, and a reproducible audit trail** — with a human-in-the-loop review step and round-trip export to the tools people already use (FlowJo, R, Prism). We orchestrate proven open-source engines rather than reinventing algorithms; our value is the usable, reproducible, trustworthy workflow wrapped around them. We are explicitly an **analysis** tool, not an acquisition or cell-sorting tool.

## The need

Manual gating — sequentially drawing polygons on 2-D scatter plots — is still the dominant analysis method, and its weaknesses are well documented and directly felt by our team. It is slow; it scales badly as panels grow, because a spectral panel has far more marker combinations than anyone can inspect pairwise; and it is subjective, so different operators (and the same operator on different days) produce different gates. This inter-analyst variability is the headline reproducibility problem in the field ([Saeys et al. 2016](https://doi.org/10.1038/nri.2016.56)). The counterpoint that justifies automation is now more than a decade old: the community-wide FlowCAP benchmark showed automated methods can **match or exceed expert manual gating**, with algorithm ensembles as reliable as human experts ([Aghaeepour et al. 2013](https://doi.org/10.1038/nmeth.2365)). Despite that, automation under-penetrates routine practice, because the good tools require code.

Spectral cytometry sharpens every part of this. Panels are large, unmixing quality and instrument drift make cross-batch comparability genuinely hard, and the analysis pain is concentrated in exactly the high-dimensional, batch-sensitive, at-scale regime where existing free tools are weakest. That concentration is the opportunity.

## What already exists, and the gap we target

The landscape splits cleanly, and understanding the split is what keeps us from building the wrong thing.

**Proven algorithms (do not rebuild these).** Clustering is dominated by FlowSOM, which a systematic comparison found to be both the best-performing and the fastest method across datasets ([Van Gassen et al. 2015](https://doi.org/10.1002/cyto.a.22625); [Weber & Robinson 2016](https://doi.org/10.1002/cyto.a.23030)), alongside PhenoGraph ([Levine et al. 2015](https://doi.org/10.1016/j.cell.2015.05.047)) and the visualization methods viSNE/UMAP ([Amir et al. 2013](https://doi.org/10.1038/nbt.2594)). Template-driven hierarchical gating that reproduces manual logic is handled by OpenCyto ([Finak et al. 2014](https://doi.org/10.1371/journal.pcbi.1003806)). Batch effects — the quiet dealbreaker for any multi-run study — are addressed by CytoNorm ([Van Gassen et al. 2019](https://doi.org/10.1002/cyto.a.23904); [2.0, 2025](https://doi.org/10.1002/cyto.a.24910)) and cyCombine ([Pedersen et al. 2022](https://doi.org/10.1038/s41467-022-29383-5)). Differential testing — the scientifically valuable endpoint — is handled by diffcyt ([Weber et al. 2019](https://doi.org/10.1038/s42003-019-0415-5)) and Citrus ([Bruggner et al. 2014](https://doi.org/10.1073/pnas.1408792111)). These are mature and excellent. Our job is to wrap them, not compete with them.

**Existing software, and where it falls short.** Commercial desktop tools (FlowJo, FCS Express) and cloud platforms (OMIQ/Dotmatics, Cytobank) are polished but carry recurring per-seat cost or require uploading data to a vendor cloud. Free tools exist — the browser-based, client-side floreada.io; the desktop GUI EasyFlow; the code libraries FlowKit and Cytoflow — but they cluster at the easy end. The documented pattern is that free desktop tools handle the basics (open a file, draw a gate, see a histogram) and fall off a cliff the moment you need spectral unmixing, automated gating, batch template application, deep hierarchical gating, high-parameter panels, or multi-user scale. **That cliff is exactly our target: spectral, automated, batch-corrected, high-dimensional, at scale — no code.**

## Scope decisions (already made, stated for the record)

1. **FCS file in, post-run only.** Every instrument, whatever its proprietary acquisition software, exports the ISAC-standard FCS file. We meet the data there. We never integrate with FACSDiva, SpectroFlo, ID7000 software, or any instrument controller — we ingest what they export. One well-tested FCS reader makes us instrument-agnostic in one stroke.
2. **Analysis, not sorting.** Sort decisions are made in the instrument's firmware microseconds before a droplet breaks off, driven by proprietary electronics; there is no external API to inject gating logic into that path, and the safety/regulatory surface makes it untouchable for a third-party tool. We own everything *after* the file is written. Note that sorter experiments still produce FCS files, so we still analyze that data — we are just never in the sort loop.
3. **Interoperate with FlowJo, do not replace it (v1).** FlowJo remains where biologists look at and defend their gates. We hand results back as named, editable gates via the open GatingML 2.0 standard and FlowJo workspace (`.wsp`) format, so our automated output opens inside the tool they trust. Two front doors, one engine: a standalone no-code web app, and optionally a FlowJo plugin.
4. **Unmixed FCS as the v1 input; in-app unmixing is a v2 option.** Biologists unmix in vendor software today (e.g. SpectroFlo → unmixed FCS → FlowJo). We start from the unmixed file. Owning unmixing ourselves is a real differentiator but adds QC burden; defer it.

## Cost framing (how to pitch "free" honestly)

FlowJo is not $5K/seat for us — through academic site licenses it runs roughly $220–$350 per seat per year. The real argument is total cost of ownership at scale: that cost is per-seat, annual, mandatory-subscription, and multiplies across a facility (30 users ≈ $7–10K/year in perpetuity). Our advantages are **no per-seat cost, local/on-prem data control** (versus the cloud tools' privacy tradeoff), transparency, and customization. The critical caveat: "free" only holds if the tool is genuinely low-friction to deploy. A free tool that needs an R environment and a sysadmin to stand up is not free in practice. **One-click/one-command deployment is part of the product, not an afterthought.**

## What we will build (v1)

A no-code web application, deployable locally or as a facility-hosted instance, implementing a guided pipeline:

**Drop in a folder of unmixed FCS files → automatic transform/QC → spectral-aware quality flags → normalization / batch correction → automated gating (template-based and/or clustering) → human-in-the-loop review and gate editing → population tables + differential statistics → reproducibility bundle (GatingML + report + parameters + versions).**

The four features that make it *trusted rather than rejected*, and that existing free tools lack in combination:
- **Human-in-the-loop, named gates.** Overlay automated gates on familiar 2-D plots; let the user drag a boundary, rename a population, map a cluster to a canonical cell type, and re-run downstream. No pure black box.
- **Reproducibility and audit by default.** Every run emits a machine- and human-readable record (inputs + checksums, panel/markers, every gate and parameter, software versions, normalization settings), exportable as GatingML plus a report. This is the single most defensible differentiator for clinical/GLP/publication use, and exactly what manual workflows cannot produce.
- **Batch correction as a first-class, visible step** with before/after diagnostics — the capability manual and free-desktop workflows handle worst.
- **Interoperability out.** GatingML / `.wsp` / CSV export so results flow into FlowJo, Prism, and R.

## Where we demonstrate impact

Three measurable demonstrations, each attacking a documented complaint:
1. **Concordance at a fraction of the time.** On already-manually-gated internal experiments, show the tool reproduces expert population frequencies (correlation / Bland–Altman on key populations) while cutting hands-on time from hours to minutes — the FlowCAP result, reproduced on our panels.
2. **Inter-operator variance collapse.** Several people analyze the same files through the tool; show population-frequency variance far below the same people gating manually. This directly quantifies the subjectivity complaint.
3. **Batch-robust cohort analysis.** Run a multi-day/multi-site dataset with and without normalization; show a treatment-associated population is stable with correction and unstable without. Most publishable, and showcases the capability others handle worst.

Public benchmark substrate exists for validation before touching internal data: the `HDCytoData` Bioconductor package (ground-truth populations) and the FlowCAP datasets.

## Licensing and IP (must clear before release)

Because our strategy is wrapping existing engines, **the license of each engine is a constraint on what we can release.** I pulled the current terms directly from each project's source. *This is factual grounding for legal counsel, not legal advice — copyleft "derivative work vs. aggregation" boundaries are genuinely contested.*

| Engine | Role | License | Class |
|---|---|---|---|
| FlowKit | FCS/GatingML/`.wsp` I/O | **BSD-3** | Permissive |
| cyCombine | batch integration | **MIT** | Permissive |
| diffcyt | differential testing | **MIT** | Permissive |
| flowCore / flowDensity | core FCS structures / density gating | **Artistic-2.0** | Permissive |
| FlowSOM | clustering (the standard) | **GPL ≥2** | Strong copyleft |
| CytoNorm | normalization | **GPL ≥2** | Strong copyleft |
| PeacoQC | QC | **GPL ≥3** | Strong copyleft |
| Cytoflow | analysis/GUI | **GPL-2.0-or-later** | Strong copyleft |
| openCyto / flowWorkspace / CytoML / cytolib | template gating, gating engine, GatingML-in-R | **AGPL-3.0** | Network copyleft |

**The decisive finding: the openCyto stack is AGPL-3.0, which collides with a web frontend.** AGPL's network clause requires that users who interact with the code *over a network* be offered the complete source of the entire combined work — written for exactly the SaaS/web-app scenario we're building. Linking those packages into a hosted tool means the conservative reading makes the whole tool AGPL. Combined with FlowSOM and CytoNorm being GPL, our license is effectively decided by three engines. Three honest paths:

1. **Embrace copyleft.** Release the whole tool as **AGPL-3.0**. Use everything, wrap freely. Lowest legal risk, fully consistent with an open-source mission; cost is no future proprietary/closed derivative and some industry-partner hesitancy.
2. **Permissive core, quarantine copyleft.** Distribute a **BSD/MIT** core (FlowKit + flowCore + cyCombine + diffcyt) and treat FlowSOM/CytoNorm/openCyto as *optional, user-installed, separately-invoked* components called as external processes. Whether process-separation escapes copyleft is **the exact question for counsel** — do not build the strategy on the assumption it holds until a lawyer signs off.
3. **Permissive core with permissive substitutes.** Reimplement the tractable engines from their published papers under our own license (copyright protects code, not methods; SOM/k-means/kNN-graph clustering are decades old). Clustering is the reimplementable one; cyCombine (MIT) already covers batch correction; CytoNorm is the harder substitution. Run a targeted patent check on anything reimplemented.

**Cleanly safe regardless:** reading/writing FCS, GatingML, and `.wsp` (file formats are not copyrightable; GatingML is an open ISAC standard; FlowKit already does all three under BSD). **FlowJo plugins: anyone can build and distribute one** — FlowJo publishes an open plugin API, you compile a Java `.jar` against their SDK, and you choose your plugin's license; the only catch is it runs only inside licensed FlowJo and R-backed plugins shell out to a local R install.

**Recommendation:** target **Path 2, with Path 1 as the committed fallback.** Design a permissive core; have counsel rule on the process-separation boundary; if it doesn't hold cleanly, ship the whole tool as AGPL-3.0. Either way, file-format interop and the FlowJo plugin proceed unencumbered.

---

# Part B — Engineering specification

*General spec / scope of engineering need, not a final design. Intended to size the effort and frame build decisions.*

## Architecture overview

A **browser UI + local compute backend** hybrid. The UI is code-free and cross-platform; the backend runs the heavy R/Python engines next to the data. This keeps data local (privacy) and avoids asking biologists to install R.

```
┌─────────────────────────────────────────────────────────────┐
│  Browser UI (no-code)                                        │
│  file drop · plot canvas · gate editor · QC/batch dashboards │
│  run config · results tables · export                        │
└───────────────▲───────────────────────────┬─────────────────┘
                │ REST/WebSocket (JSON)      │
┌───────────────┴───────────────────────────▼─────────────────┐
│  Backend API service (Python / FastAPI)                      │
│  job orchestration · session/state · provenance recorder     │
├──────────────────────────────────────────────────────────────┤
│  Analysis engine layer                                       │
│   FCS/GatingML/.wsp I/O ── FlowKit (BSD)                      │
│   transforms/compensation ── FlowKit / flowCore              │
│   QC ── PeacoQC-style checks (or reimpl)                      │
│   normalization/batch ── CytoNorm / cyCombine                │
│   automated gating ── openCyto templates / flowDensity       │
│   clustering ── FlowSOM / PhenoGraph / UMAP                  │
│   differential stats ── diffcyt                              │
│   [R engines invoked as isolated subprocesses — see IP]      │
├──────────────────────────────────────────────────────────────┤
│  Storage: local filesystem / object store                    │
│  FCS cache · run artifacts · provenance DB (SQLite/Postgres) │
└──────────────────────────────────────────────────────────────┘
```

The R engines are called as **separate processes over a file/JSON boundary**, not linked in-process. This is both an engineering choice (Python UI/orchestration, best-of-breed R algorithms) and the **licensing quarantine boundary** from Path 2 — the two align, which is convenient, but the boundary's legal sufficiency is a counsel question, not an engineering one.

## Technology stack (recommended)

- **Backend / orchestration:** Python 3.11+, FastAPI, a task queue (Celery/RQ or a lightweight async runner) for long jobs.
- **FCS / gate I/O:** FlowKit (BSD) — native FCS 3.x, GatingML 2.0, and FlowJo `.wsp` round-trip. This is the interoperability keystone; do not reimplement it.
- **Numerics / clustering:** NumPy/SciPy/scikit-learn; FlowSOM and PhenoGraph via their packages or reimplementation (see IP paths); UMAP via `umap-learn`.
- **R engines (subprocess):** CytoNorm, openCyto, diffcyt, PeacoQC, called via a thin R script harness reading/writing files + JSON. Requires a managed R environment on the backend host.
- **Frontend:** a single-page app (React/Vue) with a high-performance plotting layer capable of rendering millions of events (WebGL-based scatter, e.g. via a datashading/binning step server-side so the browser plots density rasters, not raw points).
- **Provenance store:** SQLite for single-user/local; Postgres for a facility instance.
- **Packaging/deploy:** containerized (Docker/Compose) for one-command facility hosting; a bundled desktop build (e.g. Tauri/Electron wrapping the local server) for the single-user "just works" case.

## Core components and requirements

1. **Ingestion & session.** Accept a folder/batch of FCS files. Parse keywords/metadata, detect panel (markers, fluorophores), detect raw-vs-unmixed, group into experiments. Validate and surface bad/incomplete files early. *Requirement: robust to vendor keyword quirks across Cytek/Sony/BD exports.*
2. **Transform & compensation.** Apply arcsinh/logicle transforms; handle already-unmixed spectral data (v1). Sensible auto-defaults with manual override. *v2: in-app unmixing from single-stain controls.*
3. **QC.** Per-file quality flags: event-rate discontinuities, margin/boundary events, signal drift, anomalous files in a batch. Present as a dashboard with drill-down, not a pass/fail black box.
4. **Normalization / batch correction.** First-class guided step with before/after diagnostics (per-marker distributions, UMAP colored by batch). Support control-based (CytoNorm) and control-free / integration (cyCombine) modes.
5. **Automated gating.** Two modes: (a) **template/hierarchical** — apply a named gating hierarchy across all files reproducibly (openCyto/flowDensity paradigm), importable from an existing FlowJo strategy; (b) **unsupervised clustering** — FlowSOM/PhenoGraph metaclusters with UMAP embedding.
6. **Human-in-the-loop review.** Overlay automated gates/clusters on 2-D plots; edit boundaries, rename, merge/split, map clusters → canonical populations; re-run downstream from any edit. *This is the hardest and most important UI surface.*
7. **Differential statistics.** Differential abundance and state across conditions (diffcyt); population frequency tables; exportable stats.
8. **Provenance & export.** Emit the reproducibility bundle (inputs+checksums, panel, all gates/params, versions, normalization settings) as a human report + machine record; export gates as GatingML/`.wsp` and data/stats as CSV.

## Data-flow / provenance contract

Every run is a directed pipeline whose every node records inputs, parameters, engine version, and outputs. The provenance record must be sufficient to **re-run the analysis identically** and to **explain any single population** back to the file, gate, and parameters that produced it. Treat this as a hard invariant from day one — retrofitting provenance onto an existing pipeline is far more expensive than building it in.

## Non-functional requirements

- **Scale:** handle cohorts of hundreds of FCS files and panels of 30–50 markers; millions of events per file. Plotting must stay interactive at that scale (server-side binning).
- **Deployment:** one-command local/facility install; no requirement for the end user to touch R/Python. A working R environment is a backend deployment concern, containerized.
- **Data locality:** no mandatory cloud upload; on-prem/local by default.
- **Auditability:** provenance on by default, not opt-in.
- **Cross-platform UI:** browser-based, so Windows/Mac/Linux are equal.

## Phasing

- **Phase 0 — spike & de-risk (weeks).** FlowKit round-trip (FCS in, GatingML/`.wsp` out) proven on real internal spectral files; R-subprocess harness proven with one engine (e.g. FlowSOM or CytoNorm); server-side million-event plotting proven. Counsel engaged on the Path-2 boundary in parallel.
- **Phase 1 — MVP.** Ingestion → transform → clustering (FlowSOM+UMAP) → review/edit → frequency tables → provenance bundle + CSV/GatingML export. Deployable container. Enough to run demonstration #1 (concordance).
- **Phase 2 — the differentiators.** Batch correction with diagnostics; template/hierarchical gating with FlowJo-strategy import; differential statistics. Enables demonstrations #2 and #3.
- **Phase 3 — reach & polish.** FlowJo plugin front door; optional in-app unmixing; facility multi-user instance.

## Key risks

- **The interactive gate-editor UI is the hardest single piece** and the one existing free tools do well — budget for it, and lean on it being *automated-first with edit-on-top* rather than a from-scratch manual-gating clone.
- **Licensing boundary (Path 2) may not hold**; the mitigation is the committed AGPL fallback, so the project is not blocked either way — but decide before public release, not after.
- **R-subprocess operational complexity** (environment management, versioning, error surfacing across the language boundary) is real; containerization and a disciplined harness contain it.
- **Vendor FCS quirks** across instruments will need real files to shake out — start Phase 0 with actual exports from every machine our biologists use.
- **Vendor consolidation** (Danaher owns Cytek; BD owns FlowJo) is a reason to build strictly on the open FCS/GatingML standards, which keeps us neutral and is our honest differentiator versus vendor-locked platforms.

## Net

The algorithms are solved and free; the trustworthy, reproducible, no-code workflow around them for **spectral, batch-corrected, at-scale** analysis is the unmet need. Build a permissive-core (AGPL-fallback) Python backend that orchestrates FlowKit + FlowSOM + CytoNorm/cyCombine + openCyto + diffcyt behind a no-code browser UI, with human-in-the-loop editing and a provenance bundle as the headline features, and prove it on concordance, operator-variance, and batch-robustness benchmarks.
