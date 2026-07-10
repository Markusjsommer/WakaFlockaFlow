"""Functional-state scoring for clustered populations.

Composition ("what cell type") answers *what* a population is. State answers
*what it is doing*: activation, exhaustion, memory/differentiation,
proliferation, cytotoxicity, signaling. Each axis is a small, transparent marker
signature. For a set of populations we robustly z-score every marker's median
across populations (same approach as cell-type annotation), then score each axis
as (mean z of its positive markers) - (mean z of its negative markers).

An axis is only reported when at least one of its markers is present in the
panel, so this degrades gracefully on any panel. Purely additive: it reads the
per-population medians already computed, no reclustering.
"""
from __future__ import annotations

import re

import numpy as np


def _key(label: str) -> str:
    """Normalize a marker label for matching. Strips a trailing fluorophore area
    suffix only when separated (``-A``/``_H``/`` W``) so real names like CD45RA
    or TIGIT are preserved; removes punctuation; uppercases."""
    s = str(label or "").strip()
    s = re.sub(r"[-_ ][AHW]$", "", s, flags=re.IGNORECASE)
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()


def _keys(*names) -> list[str]:
    return [_key(n) for n in names]


# Each axis: positive markers (up on the axis) and optional negative markers
# (down). Synonyms are matched by normalized key.
FUNCTIONAL_AXES: list[dict] = [
    {
        "name": "Activation",
        "positive": _keys("CD25", "CD69", "HLA-DR", "CD38"),
        "negative": [],
    },
    {
        "name": "Exhaustion",
        "positive": _keys("PD-1", "CD279", "TIM-3", "CD366", "LAG-3", "CD223",
                          "TIGIT", "CTLA-4", "CD152"),
        "negative": [],
    },
    {
        # High = memory/experienced; low CD45RA/CCR7 = not naive.
        "name": "Memory",
        "positive": _keys("CD45RO"),
        "negative": _keys("CD45RA", "CCR7", "CD197"),
    },
    {
        "name": "Proliferation",
        "positive": _keys("Ki-67", "MKI67", "CD71"),
        "negative": [],
    },
    {
        "name": "Cytotoxicity",
        "positive": _keys("Granzyme B", "GZMB", "Perforin", "PRF1",
                          "CD107a", "LAMP1"),
        "negative": [],
    },
    {
        "name": "Signaling",
        "positive": _keys("pSTAT1", "pSTAT3", "pSTAT5", "pERK", "pS6", "pAKT"),
        "negative": [],
    },
]


def _zscore_matrix(populations: list[dict]):
    """Robust per-marker z-scores across populations. Returns (zmat, key_index)
    where key_index maps a normalized marker key -> column in zmat."""
    # Union of marker keys across populations (first population usually has all).
    keys: list[str] = []
    seen = set()
    key_to_channel: dict[str, str] = {}
    for p in populations:
        for ch in (p.get("median_expression") or {}):
            k = _key(ch)
            if k and k not in seen:
                seen.add(k)
                keys.append(k)
                key_to_channel[k] = ch

    med = np.full((len(populations), len(keys)), np.nan, dtype=float)
    for i, p in enumerate(populations):
        me = p.get("median_expression") or {}
        # map channel -> key value (first channel wins per key)
        by_key = {}
        for ch, v in me.items():
            k = _key(ch)
            if k and k not in by_key:
                by_key[k] = v
        for j, k in enumerate(keys):
            if k in by_key:
                try:
                    med[i, j] = float(by_key[k])
                except (TypeError, ValueError):
                    pass

    zmat = np.zeros_like(med)
    for j in range(med.shape[1]):
        col = med[:, j]
        good = col[~np.isnan(col)]
        if good.size < 2:
            continue
        c = np.nanmedian(col)
        mad = np.nanmedian(np.abs(col - c)) * 1.4826
        scale = mad if mad > 1e-9 else (np.nanstd(col) or 1.0)
        zmat[:, j] = (col - c) / scale
    zmat = np.nan_to_num(zmat, nan=0.0)
    return zmat, {k: j for j, k in enumerate(keys)}, set(keys)


def score_axes(populations: list[dict], high_threshold: float = 0.6) -> list[list[dict]]:
    """Score each functional axis for every population.

    Returns a list parallel to ``populations``; each element is a list of
    ``{"name","score","call","markers"}`` for the axes whose markers are present
    in the panel. ``call`` is True when the population is high on that axis
    (score >= high_threshold), which the UI surfaces as a chip.
    """
    if not populations:
        return []
    zmat, key_index, available = _zscore_matrix(populations)

    out: list[list[dict]] = []
    for i in range(len(populations)):
        axes = []
        for axis in FUNCTIONAL_AXES:
            pos = [k for k in axis["positive"] if k in available]
            neg = [k for k in axis["negative"] if k in available]
            if not pos:
                continue  # panel can't measure this axis
            pos_z = float(np.mean([zmat[i, key_index[k]] for k in pos]))
            neg_z = float(np.mean([zmat[i, key_index[k]] for k in neg])) if neg else 0.0
            score = pos_z - neg_z
            contributing = [k for k in pos if zmat[i, key_index[k]] >= high_threshold]
            axes.append({
                "name": axis["name"],
                "score": round(score, 2),
                "call": bool(score >= high_threshold),
                "markers": contributing,
            })
        out.append(axes)
    return out
