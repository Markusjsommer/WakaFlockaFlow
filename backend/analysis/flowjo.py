"""FlowJo interoperability export for automated populations.

Turns a clustering run into a FlowJo-openable bundle: an *augmented* FCS file
carrying an extra integer ``Population`` parameter (metacluster id + 1 per cell)
plus a FlowKit :class:`~flowkit.GatingStrategy` in which every population is a
named 1-D :class:`RectangleGate` on that ``Population`` parameter. Because the
gate ranges bracket a single integer value ([n-0.5 .. n+0.5]) each gate selects
exactly one cluster, so opening ``workspace.wsp`` in FlowJo reproduces the
tool's populations as named gates.

Everything is built with the verified FlowKit 1.3.2 write API:
  * ``fk.Sample(array, channel_labels=...)``            - augmented FCS in memory
  * ``Sample.export(name, source="raw", directory=...)``- write analyzed.fcs
  * ``fk.Dimension("Population", range_min, range_max)``- 1-D range on Population
  * ``fk.gates.RectangleGate(name, dimensions=[dim])``  - one gate per population
  * ``GatingStrategy.add_gate(gate, gate_path=("root",))``
  * ``Session.export_wsp(path, group_name)``            - FlowJo workspace
  * ``fk.export_gatingml(gating_strategy, path)``       - GatingML 2.0

Gates operate on uncompensated, untransformed events (``compensation_ref=
"uncompensated"``, ``transformation_ref=None``) so the integer Population values
are matched verbatim.

Naming: the FlowJo workspace uses the population's human label (e.g. "CD8 T
cell") as the gate name -- FlowKit stores it as the ``<Population name=...>`` so
FlowJo displays it verbatim. The portable GatingML document is exported from a
parallel strategy whose gate ids are sanitized to valid XML ``xs:ID`` (NCName)
tokens, because GatingML 2.0 forbids spaces/punctuation in ``gating:id`` and a
space-bearing id produces a document that fails schema validation (and so cannot
be re-parsed). Both strategies define the identical gates, so gate membership /
counts are the same in either file.
"""
from __future__ import annotations

import os
import re

import numpy as np
import flowkit as fk

# Name of the synthetic parameter appended to the FCS that encodes the cluster id.
POPULATION_PARAM = "Population"


def _dedupe(candidates: list, fallback) -> list:
    """Return the candidate strings made unique, disambiguating collisions.

    ``fallback(i)`` supplies a base label for the i-th entry when its candidate is
    empty. Colliding entries get an incrementing ``" (N)"`` suffix.
    """
    seen: set[str] = set()
    out: list[str] = []
    for i, cand in enumerate(candidates):
        base = (str(cand).strip() if cand is not None else "") or str(fallback(i))
        name = base
        n = 2
        while name in seen:
            name = f"{base} ({n})"
            n += 1
        seen.add(name)
        out.append(name)
    return out


def _ncname(text: str) -> str:
    """Coerce ``text`` into a valid XML ``xs:ID`` (NCName) token for GatingML ids.

    NCName: starts with a letter or ``_``; remaining chars are letters, digits,
    ``-``, ``.`` or ``_``. Every other character (spaces, ``+``, ``(``, ...) is
    replaced with ``_``; a leading non-letter/underscore is prefixed with ``P_``.
    """
    s = re.sub(r"[^0-9A-Za-z_.\-]", "_", str(text)).strip("_") or "pop"
    if not re.match(r"[A-Za-z_]", s[0]):
        s = "P_" + s
    return s


def _display_gate_names(populations: list) -> list:
    """Human gate names (cell-type labels) for the FlowJo workspace, made unique."""
    return _dedupe(
        [p.get("name") for p in populations],
        fallback=lambda i: f"Population {int(populations[i]['metacluster_id']) + 1}",
    )


def _build_strategy(populations: list, gate_names: list) -> "fk.GatingStrategy":
    """One RectangleGate per population on the Population parameter, under root."""
    gs = fk.GatingStrategy()
    for pop, gate_name in zip(populations, gate_names):
        mc = int(pop["metacluster_id"])
        value = mc + 1  # Population parameter holds metacluster_id + 1
        dim = fk.Dimension(
            POPULATION_PARAM,
            compensation_ref="uncompensated",
            transformation_ref=None,
            range_min=value - 0.5,
            range_max=value + 0.5,
        )
        gs.add_gate(fk.gates.RectangleGate(gate_name, dimensions=[dim]), gate_path=("root",))
    return gs


def _build_marker_strategy(populations, gate_names, gate_paths) -> "fk.GatingStrategy":
    """One multi-dimensional RectangleGate per population on the REAL marker
    channels: the AND of its gate-path constraints (from gatepaths.derive). Open
    sides are closed with the data axis bounds so GatingML/.wsp stay valid.
    Populations without a derived path fall back to the Population-parameter gate.
    """
    gs = fk.GatingStrategy()
    for pop, gate_name in zip(populations, gate_names):
        mc = int(pop["metacluster_id"])
        gp = gate_paths.get(mc) or gate_paths.get(str(mc))
        steps = gp.get("steps") if gp else None
        if not steps:
            value = mc + 1
            dim = fk.Dimension(POPULATION_PARAM, compensation_ref="uncompensated",
                               transformation_ref=None,
                               range_min=value - 0.5, range_max=value + 0.5)
            gs.add_gate(fk.gates.RectangleGate(gate_name, dimensions=[dim]), gate_path=("root",))
            continue
        dims = []
        for s in steps:
            lo = s["lo"] if s.get("lo") is not None else s["axis_min"]
            hi = s["hi"] if s.get("hi") is not None else s["axis_max"]
            if hi <= lo:
                hi = lo + 1e-6
            dims.append(fk.Dimension(str(s["marker"]), compensation_ref="uncompensated",
                                     transformation_ref=None, range_min=float(lo), range_max=float(hi)))
        gs.add_gate(fk.gates.RectangleGate(gate_name, dimensions=dims), gate_path=("root",))
    return gs


def build_flowjo_export(events, channel_names, labels, populations, outdir,
                        gate_paths=None) -> dict:
    """Build a FlowJo interoperability bundle for one clustering run.

    Args:
        events:        ndarray (n_events, n_channels) of the run's event matrix.
        channel_names: list[str] $PnN channel names, one per column of ``events``.
        labels:        per-cell metacluster id array (int), length n_events.
        populations:   list of dicts ``{"metacluster_id": int, "name": str}``.
        outdir:        directory to write analyzed.fcs / workspace.wsp / gating.xml.

    Returns:
        {"fcs": <path>, "wsp": <path>, "gatingml": <path>} absolute paths.
    """
    os.makedirs(outdir, exist_ok=True)

    events = np.asarray(events, dtype=np.float32)
    labels = np.asarray(labels).astype(int)
    if events.shape[0] != labels.shape[0]:
        raise ValueError(
            f"events/labels length mismatch: {events.shape[0]} vs {labels.shape[0]}"
        )

    # --- augmented FCS: original events + a "Population" parameter (id + 1) -------
    pop_col = (labels + 1).astype(np.float32).reshape(-1, 1)
    aug_events = np.hstack([events, pop_col])
    aug_names = list(channel_names) + [POPULATION_PARAM]

    sample = fk.Sample(
        aug_events,
        sample_id="analyzed.fcs",
        channel_labels=aug_names,
        # keep every event so gate counts reflect the full run, not a subsample.
        subsample=int(aug_events.shape[0]) or 1,
    )
    sample.export("analyzed.fcs", source="raw", directory=outdir)
    fcs_path = os.path.abspath(os.path.join(outdir, "analyzed.fcs"))

    # --- FlowJo workspace (.wsp): gates named by cell type (spaces are fine) -----
    # With gate_paths, gates are real marker-threshold rectangles; otherwise a
    # single gate per cluster on the synthetic Population parameter.
    def strategy(names):
        return (_build_marker_strategy(populations, names, gate_paths)
                if gate_paths else _build_strategy(populations, names))

    display_names = _display_gate_names(populations)
    session = fk.Session(gating_strategy=strategy(display_names), fcs_samples=[sample])
    wsp_path = os.path.abspath(os.path.join(outdir, "workspace.wsp"))
    session.export_wsp(wsp_path, "All Samples")

    # --- GatingML 2.0 (.xml): gate ids sanitized to valid xs:ID / NCName ---------
    gml_names = _dedupe([_ncname(n) for n in display_names], fallback=lambda i: f"pop{i}")
    gml_path = os.path.abspath(os.path.join(outdir, "gating.xml"))
    fk.export_gatingml(strategy(gml_names), gml_path)

    return {"fcs": fcs_path, "wsp": wsp_path, "gatingml": gml_path}
