# NOTICE

**WakaFlockaFlow** is free software licensed under the **GNU Affero General Public
License, version 3.0 (AGPL-3.0-or-later)**. See [`LICENSE`](LICENSE) for the full
license text.

Copyright (C) 2026 The WakaFlockaFlow contributors.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. Because it is AGPL-licensed, if you run a modified version of
this software to offer a network service, you must also offer the corresponding
source of your modified version to the users of that service.

---

## Wrapped / third-party engines

WakaFlockaFlow orchestrates several established flow-cytometry and machine-learning
libraries. Each remains under its own license and copyright; they are dependencies,
not part of this project's source. AGPL-3.0 is compatible with (and, where combined,
governs the aggregate of) the components below.

| Component | Role in the pipeline | License |
|-----------|----------------------|---------|
| **FlowKit** | FCS I/O + arcsinh/logicle transforms (Python) | BSD-3-Clause |
| **FlowSOM** (Python port) | Self-organizing-map + metaclustering for population identification | GPL-2.0-or-later |
| **umap-learn** | UMAP dimensionality reduction for the 2-D embedding | BSD-3-Clause |
| **PeacoQC** | Signal-quality control / anomaly removal | GPL-3.0-or-later |
| **CytoNorm** | Batch normalization across acquisitions | GPL-2.0-or-later |
| **openCyto / CytoML** | Gating-strategy and gatingML/FlowJo interchange | AGPL-3.0 |
| **diffcyt** | Differential-abundance / differential-state testing | MIT |
| **flowCore** | Core R data structures for cytometry | Artistic-2.0 |

Additional common Python dependencies (FastAPI, Uvicorn, NumPy, SciPy, pandas,
scikit-learn, SQLAlchemy, Pydantic, anndata, PyArrow) are distributed under their
respective permissive licenses (MIT / BSD / Apache-2.0). Their license texts are
available in the corresponding installed packages.

---

## Bundled test data, NOT redistributed

The 40-color spectral reference acquisition used during development
(`PBMC_40color_E1_UNMIXED.fcs`, "phitonex E1") is licensed **CC BY-ND**
(Creative Commons Attribution-NoDerivatives). Because that license forbids
distributing derivative/modified versions, this data file is **kept local and is
git-ignored**: it is **not** included in this repository or in any release
artifact. See [`.gitignore`](.gitignore).

## Bundled demo data, flowSpecs (permissive, redistributed)

The repository **does** bundle a small, permissively-licensed demo set: the
**flowSpecs** example spectral data (**Artistic-2.0**), exported to FCS and kept
under [`sample_data/spectral_pbmc/`](sample_data/spectral_pbmc/). Artistic-2.0 is
compatible with AGPL-3.0, so this set is safe to ship; it powers the out-of-the-box
demo (`fullPanel.fcs`). Source: <https://bioconductor.org/packages/flowSpecs/>.

To analyze your own data, drop `.fcs` files into `./fcs/` and run
`docker compose up` (see [`README.md`](README.md)), they are registered alongside
the bundled demo, and nothing leaves your machine.

## Bundled synthetic demo cohort

[`sample_data/differential_demo/`](sample_data/differential_demo/) contains eight
**synthetic** FCS files (not real biology) derived from the flowSpecs demo by
[`scripts/make_differential_demo.py`](scripts/make_differential_demo.py). They
carry a planted group difference so the differential-analysis workflow can be run
end to end with a known ground truth. Clearly labelled `SYN_*` and documented as
synthetic; safe to redistribute (derived from the Artistic-2.0 flowSpecs set).

## Bundled UI asset

The loading animation ([`frontend/public/bongo-loading.gif`](frontend/public/bongo-loading.gif))
is a "Bongo Cat" GIF, used under a permissive license per the project maintainer.
Bongo Cat originates with StrayRogue (art) and DitzyFlama (animation).
