"""FCS I/O and marker helpers built on flowkit.

Fluorescence columns are arcsinh-transformed on load (optional); Time and
FSC/SSC scatter columns are always left untransformed.
"""
import os

import numpy as np
import flowkit as fk


def _is_scatter_or_time(name: str) -> bool:
    """True for the Time channel or any scatter (FSC/SSC) channel."""
    n = name.upper()
    return n == "TIME" or "FSC" in n or "SSC" in n


def load_events(path: str, transform: bool = True, cofactor: float = 150.0):
    """Read an FCS file.

    Returns:
        events:        float32 ndarray of shape (n_events, n_channels)
        channel_names: list[str] from $PnN
        marker_labels: list[str] from $PnS (falls back to $PnN when empty)

    When ``transform`` is True, applies arcsinh(x / cofactor) to fluorescence
    columns only (Time and FSC/SSC scatter columns are left untouched).
    """
    sample = fk.Sample(path)

    events = np.asarray(sample.get_events(source="raw"), dtype=np.float32)

    channel_names = [str(n) for n in sample.pnn_labels]

    pns_labels = list(sample.pns_labels)
    marker_labels = []
    for nn, ns in zip(channel_names, pns_labels):
        ns = str(ns).strip() if ns is not None else ""
        marker_labels.append(ns if ns else nn)

    if transform:
        events = events.copy()
        for i, nm in enumerate(channel_names):
            if not _is_scatter_or_time(nm):
                events[:, i] = np.arcsinh(events[:, i] / cofactor)

    return events, channel_names, marker_labels


def write_fcs(events: np.ndarray, channel_names: list, path: str) -> None:
    """Write ``events`` to an FCS file at ``path`` via flowkit."""
    events = np.asarray(events, dtype=np.float32)
    sample = fk.Sample(events, sample_id=os.path.basename(path), channel_labels=list(channel_names))

    abspath = os.path.abspath(path)
    directory = os.path.dirname(abspath)
    filename = os.path.basename(abspath)
    if directory:
        os.makedirs(directory, exist_ok=True)

    sample.export(filename, source="raw", directory=directory)


def marker_indices(channel_names: list, exclude_scatter: bool = True) -> list:
    """Return indices of fluorophore marker columns.

    Always excludes the Time channel; when ``exclude_scatter`` is True (default)
    also excludes any channel whose name contains FSC or SSC.
    """
    idx = []
    for i, nm in enumerate(channel_names):
        u = str(nm).upper()
        if u == "TIME":
            continue
        if exclude_scatter and ("FSC" in u or "SSC" in u):
            continue
        idx.append(i)
    return idx
