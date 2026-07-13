"""Automatic cell-type annotation for clustered populations.

Transparent, rule-based labeller: each canonical cell type is a signature of
positive/negative markers. For a set of populations we z-score every marker's
median across populations, decide which markers are high/low per population,
then score each population against every signature and assign the best match.

No training, no reference dataset - auditable and editable, matching the tool's
"named, defensible populations" thesis. Extend CELL_TYPES to recognise more.

Panel-agnostic: the caller supplies a channel->marker mapping (identity when the
FCS already carries marker names), so this works on any panel once markers are named.
"""

from __future__ import annotations

import math
import re

import numpy as np


# --------------------------------------------------------------------------- signatures
# Each signature: positive markers (should be high), negative markers (should be low),
# and `anchors` = markers that MUST be present+high for the call to be considered
# (lineage gate). Order is roughly specific -> general; ties break toward more anchors.
CELL_TYPES: list[dict] = [
    # ---- T cells -------------------------------------------------------------
    {"name": "Regulatory T cell", "anchors": ["CD3", "CD4"],
     "positive": ["CD3", "CD4", "CD25", "FoxP3"], "negative": ["CD127", "CD8"]},
    {"name": "Naive CD4 T cell", "anchors": ["CD3", "CD4"],
     "positive": ["CD3", "CD4", "CD45RA", "CCR7", "CD27"], "negative": ["CD8", "CD45RO"]},
    {"name": "Memory CD4 T cell", "anchors": ["CD3", "CD4"],
     "positive": ["CD3", "CD4", "CD45RO"], "negative": ["CD8", "CD45RA"]},
    {"name": "CD4 T cell", "anchors": ["CD3", "CD4"],
     "positive": ["CD3", "CD4"], "negative": ["CD8", "CD19", "CD14", "CD56"]},
    {"name": "Naive CD8 T cell", "anchors": ["CD3", "CD8"],
     "positive": ["CD3", "CD8", "CD45RA", "CCR7", "CD27"], "negative": ["CD4", "CD45RO"]},
    {"name": "Memory CD8 T cell", "anchors": ["CD3", "CD8"],
     "positive": ["CD3", "CD8", "CD45RO"], "negative": ["CD4", "CD45RA"]},
    {"name": "CD8 T cell", "anchors": ["CD3", "CD8"],
     "positive": ["CD3", "CD8"], "negative": ["CD4", "CD19", "CD14", "CD56"]},
    {"name": "MAIT / Vα7.2 T cell", "anchors": ["CD3", "CD161"],
     "positive": ["CD3", "CD161", "CD8"], "negative": ["CD19", "CD14"]},
    {"name": "gamma-delta T cell", "anchors": ["CD3", "TCRgd"],
     "positive": ["CD3", "TCRgd"], "negative": ["CD4", "CD19"]},
    {"name": "NKT-like cell", "anchors": ["CD3", "CD56"],
     "positive": ["CD3", "CD56"], "negative": ["CD19", "CD14"]},
    {"name": "T cell", "anchors": ["CD3"],
     "positive": ["CD3"], "negative": ["CD19", "CD14", "CD56", "CD20"]},
    # ---- B cells -------------------------------------------------------------
    {"name": "Plasmablast", "anchors": ["CD19", "CD38"],
     "positive": ["CD19", "CD27", "CD38"], "negative": ["CD20", "CD3", "IgD"]},
    {"name": "Memory B cell", "anchors": ["CD19", "CD27"],
     "positive": ["CD19", "CD20", "CD27"], "negative": ["CD3", "IgD"]},
    {"name": "Naive B cell", "anchors": ["CD19"],
     "positive": ["CD19", "CD20", "IgD"], "negative": ["CD3", "CD27"]},
    {"name": "B cell", "anchors": ["CD19"],
     "positive": ["CD19", "CD20", "IgM"], "negative": ["CD3", "CD14", "CD56"]},
    # CD20-anchored B-cell fallback for panels that carry CD20 but not CD19
    # (common in mass-cytometry / CyTOF panels, e.g. Bodenmiller BCR-XL).
    {"name": "B cell", "anchors": ["CD20"],
     "positive": ["CD20", "CD19", "IgM", "IgD"], "negative": ["CD3", "CD14", "CD56"]},
    # ---- NK ------------------------------------------------------------------
    {"name": "CD56bright NK cell", "anchors": ["CD56"],
     "positive": ["CD56"], "negative": ["CD3", "CD16", "CD19"]},
    {"name": "CD56dim NK cell", "anchors": ["CD56", "CD16"],
     "positive": ["CD56", "CD16"], "negative": ["CD3", "CD19", "CD14"]},
    {"name": "NK cell", "anchors": ["CD56"],
     "positive": ["CD56"], "negative": ["CD3", "CD19", "CD14"]},
    # ---- Myeloid -------------------------------------------------------------
    {"name": "Non-classical monocyte", "anchors": ["CD14", "CD16"],
     "positive": ["CD16", "HLA-DR", "CD11c"], "negative": ["CD3", "CD19"]},
    {"name": "Classical monocyte", "anchors": ["CD14"],
     "positive": ["CD14", "HLA-DR", "CD11b", "CD33"], "negative": ["CD16", "CD3", "CD19"]},
    {"name": "Monocyte", "anchors": ["CD14"],
     "positive": ["CD14", "HLA-DR"], "negative": ["CD3", "CD19", "CD56"]},
    {"name": "Plasmacytoid DC", "anchors": ["CD123", "HLA-DR"],
     "positive": ["CD123", "HLA-DR"], "negative": ["CD3", "CD14", "CD11c", "CD19"]},
    {"name": "Myeloid DC", "anchors": ["CD11c", "HLA-DR"],
     "positive": ["CD11c", "HLA-DR", "CD1c"], "negative": ["CD3", "CD14", "CD19", "CD56"]},
    {"name": "Basophil", "anchors": ["CD123"],
     "positive": ["CD123"], "negative": ["HLA-DR", "CD3", "CD14"]},
    {"name": "Neutrophil", "anchors": ["CD16", "CD15"],
     "positive": ["CD16", "CD15", "CD11b"], "negative": ["CD3", "CD14", "HLA-DR"]},
    {"name": "Eosinophil", "anchors": ["CD11b"],
     "positive": ["CD11b", "Siglec-8"], "negative": ["CD16", "CD3"]},
    # ---- progenitors / other -------------------------------------------------
    {"name": "Hematopoietic progenitor", "anchors": ["CD34"],
     "positive": ["CD34"], "negative": ["CD3", "CD19", "CD14"]},
]

# Marker synonym normalisation -> canonical token used in the signatures above.
_SYNONYMS = {
    "CD8A": "CD8", "CD8B": "CD8", "CD4RA": "CD45RA",
    "HLADR": "HLA-DR", "HLA_DR": "HLA-DR", "HLA.DR": "HLA-DR",
    "FOXP3": "FoxP3", "TCRGD": "TCRgd", "TCRGAMMADELTA": "TCRgd",
    "IGD": "IgD", "IGM": "IgM", "CD1C": "CD1c",
    "CCR7": "CCR7", "CD197": "CCR7", "SIGLEC8": "Siglec-8", "SIGLEC-8": "Siglec-8",
}


def normalize_marker(name: str) -> str:
    """Map a raw marker/channel label to a canonical signature token, or '' if it
    doesn't look like a marker (fluorophore/scatter names collapse to '')."""
    if not name:
        return ""
    s = str(name).strip()
    # strip a trailing "-A"/"-H" area suffix and common fluorophore decorations
    s = re.sub(r"[-_ ]?[AHW]$", "", s)
    key = re.sub(r"[^A-Za-z0-9]", "", s).upper()
    if key in _SYNONYMS:
        return _SYNONYMS[key]
    m = re.match(r"^(CD\d+[A-Z]?)", key)
    if m:
        canon = m.group(1)
        return _SYNONYMS.get(canon, canon)
    for token in ("HLA-DR", "FoxP3", "TCRgd", "IgD", "IgM", "CCR7", "CD34", "Siglec-8", "CD1c"):
        if key == re.sub(r"[^A-Za-z0-9]", "", token).upper():
            return token
    return ""


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def annotate_populations(
    populations: list[dict],
    channel_to_marker: dict[str, str] | None = None,
    z_threshold: float = 0.4,
) -> list[dict]:
    """Assign a cell-type label to each population.

    populations: list of dicts each with `median_expression` {channel: value}.
    channel_to_marker: optional map from channel name -> marker name; when omitted,
        the channel name is treated as the marker (files that already carry markers).
    Returns a parallel list of {label, confidence, markers} (markers = the high
    canonical markers that drove the call), in population order.
    """
    if not populations:
        return []

    # Resolve the canonical marker for each channel present in the medians.
    channels = list(populations[0].get("median_expression", {}).keys())
    ch_marker: dict[str, str] = {}
    for ch in channels:
        raw = (channel_to_marker or {}).get(ch, ch)
        canon = normalize_marker(raw)
        if canon:
            ch_marker[ch] = canon
    # If several channels map to the same marker, keep the first.
    marker_channels: dict[str, str] = {}
    for ch, mk in ch_marker.items():
        marker_channels.setdefault(mk, ch)
    available = set(marker_channels)

    # Build the per-population, per-marker median matrix and robust z-score it.
    markers = sorted(available)
    med = np.array(
        [[float(p.get("median_expression", {}).get(marker_channels[mk], np.nan)) for mk in markers]
         for p in populations],
        dtype=float,
    )
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

    def z_of(pop_i: int, marker: str) -> float | None:
        if marker not in available:
            return None
        return float(zmat[pop_i, markers.index(marker)])

    out = []
    for i in range(len(populations)):
        best = None
        for sig in CELL_TYPES:
            anchors = [a for a in sig["anchors"] if a in available]
            # Anchors must be present in the panel AND expressed high on this pop.
            if len(anchors) < len(sig["anchors"]):
                continue  # panel can't distinguish this type
            if any((z_of(i, a) or -9) < z_threshold for a in anchors):
                continue
            pos = [m for m in sig["positive"] if m in available]
            neg = [m for m in sig["negative"] if m in available]
            if not pos:
                continue
            pos_score = np.mean([_sigmoid(z_of(i, m)) for m in pos])
            neg_pen = np.mean([_sigmoid(z_of(i, m)) for m in neg]) if neg else 0.0
            specificity = 0.05 * len(sig["anchors"]) + 0.02 * len(pos)  # prefer specific calls
            score = pos_score - 0.6 * neg_pen + specificity
            if best is None or score > best[0]:
                high = [m for m in pos if (z_of(i, m) or 0) >= z_threshold]
                best = (score, sig["name"], high)
        if best is None:
            out.append({"label": None, "confidence": 0.0, "markers": []})
        else:
            score, name, high = best
            out.append({
                "label": name,
                "confidence": round(min(1.0, max(0.0, (score - 0.3))), 2),
                "markers": high,
            })
    return out
