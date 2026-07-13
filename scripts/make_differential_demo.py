#!/usr/bin/env python3
"""Generate the SYNTHETIC differential-analysis demo cohort.

This is NOT real biology. It derives a small cohort from the bundled flowSpecs
demo (PBMC_spectral_UNMIXED.fcs) and PLANTS a known difference between two groups
so the differential workflow has something to detect:

  * control (n=4): bootstrap of the demo events + small replicate noise.
  * treated (n=4): same, but a CD8 T-cell subpopulation is over-represented
    (~14% -> ~38%) and CD45RA is raised within it.

Expected result after joint clustering + differential testing: the CD8 T-cell
population is significantly MORE abundant in treated (positive log2FC), and
CD45RA is the top differential-state marker in it. 4 vs 4 clears significance
even with the dependency-light Python rank-test engine (Mann-Whitney floor at
p~0.029 < 0.05); diffcyt shows it more strongly.

Deterministic (fixed seeds). Re-run to regenerate:
    ./.venv/bin/python scripts/make_differential_demo.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "backend"))
from analysis import io as aio  # noqa: E402

SRC = os.path.join(ROOT, "sample_data", "spectral_pbmc", "PBMC_spectral_UNMIXED.fcs")
OUT = os.path.join(ROOT, "sample_data", "differential_demo")
N = 8000
N_PER_GROUP = 4


def _find(chan, name):
    for i, c in enumerate(chan):
        if name.lower() in str(c).lower():
            return i
    raise ValueError(f"channel {name!r} not found")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    events, chan, _markers = aio.load_events(SRC, transform=False)
    events = np.asarray(events, dtype=np.float32)
    n0 = events.shape[0]
    i_cd8, i_cd3, i_cd45ra = _find(chan, "CD8"), _find(chan, "CD3"), _find(chan, "CD45RA")

    cd8_hi = events[:, i_cd8] > np.percentile(events[:, i_cd8], 75)
    cd3_hi = events[:, i_cd3] > np.percentile(events[:, i_cd3], 60)
    target = np.where(cd8_hi & cd3_hi)[0]
    sd = events.std(axis=0) + 1e-6

    def make(seed, treated):
        rng = np.random.default_rng(seed)
        if not treated:
            X = events[rng.choice(n0, N, replace=True)].copy()
        else:
            n_gen = int(N * 0.70)
            rows = np.concatenate([rng.choice(n0, n_gen, replace=True),
                                   rng.choice(target, N - n_gen, replace=True)])
            X = events[rows].copy()
            X[n_gen:, i_cd45ra] += 1.5 * sd[i_cd45ra]  # differential state
        X += rng.normal(0, 0.05, X.shape).astype(np.float32) * sd
        return np.clip(X, 0, None)

    for k in range(1, N_PER_GROUP + 1):
        aio.write_fcs(make(100 + k, False), chan, os.path.join(OUT, f"SYN_ctrl_{k}.fcs"))
        aio.write_fcs(make(200 + k, True), chan, os.path.join(OUT, f"SYN_treat_{k}.fcs"))
    print(f"wrote {2 * N_PER_GROUP} synthetic FCS to {OUT}")


if __name__ == "__main__":
    main()
