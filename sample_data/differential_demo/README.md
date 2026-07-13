# Synthetic differential-analysis demo cohort

**This is synthetic data, not real biology.** It exists only to demonstrate the
differential-analysis workflow end to end with a known ground truth.

## What it is

Eight FCS files derived from the bundled flowSpecs demo
(`../spectral_pbmc/PBMC_spectral_UNMIXED.fcs`) by
[`scripts/make_differential_demo.py`](../../scripts/make_differential_demo.py):

- `SYN_ctrl_1..4.fcs` (group **control**): bootstrap of the demo events plus
  small replicate noise.
- `SYN_treat_1..4.fcs` (group **treated**): same, but with a planted difference.

## Planted signal (the ground truth)

- **Differential abundance:** a CD8 T-cell subpopulation is over-represented in
  the treated group (~14% -> ~38%). It should come out as the top significant
  population with a positive log2 fold change.
- **Differential state:** CD45RA is raised within that CD8 T-cell population in
  the treated group. It should be the top differential-state marker.

## How to run it

1. **Cohort** tab -> select all eight `SYN_*` files.
2. Tag `SYN_ctrl_*` as `control` and `SYN_treat_*` as `treated`.
3. Run the cohort, then run **Differential** (Python engine works; diffcyt is
   stronger where R is available).

4 vs 4 replicates clear significance even with the Python rank-test engine.
Regenerate deterministically with
`./.venv/bin/python scripts/make_differential_demo.py`.
