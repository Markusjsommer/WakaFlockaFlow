"""Adapter: cohort clustering results -> differential-testing matrices.

The ONLY module coupled to the cohort table names. It reads ClusteringRunSample
and PopulationSampleStat for a run and returns plain dicts/lists that both the
diffcyt R recipe (written to CSV) and the Python fallback consume, so neither has
to know the ORM.
"""
from __future__ import annotations

from models_cluster import ClusteringRunSample, PopulationSampleStat, Population


def build_matrices(db, clustering_run_id: str) -> dict:
    """Assemble per-sample abundance + state matrices for a cohort run.

    Returns:
        {
          "samples": [{sample_index, sample_label, group, batch, covariates,
                       n_events_used}],           # sample metadata, sorted
          "metacluster_ids": [int, ...],          # sorted populations
          "pop_names": {metacluster_id: name},
          "counts":  {metacluster_id: {sample_index: cell_count}},
          "totals":  {sample_index: n_events_used},
          "medians": {metacluster_id: {sample_index: {marker: value}}},
          "markers": [str, ...],                   # sorted union of state markers
        }
    """
    samples = (
        db.query(ClusteringRunSample)
        .filter(ClusteringRunSample.clustering_run_id == clustering_run_id)
        .order_by(ClusteringRunSample.sample_index)
        .all()
    )
    stats = (
        db.query(PopulationSampleStat)
        .filter(PopulationSampleStat.clustering_run_id == clustering_run_id)
        .all()
    )
    pops = (
        db.query(Population)
        .filter(Population.clustering_run_id == clustering_run_id)
        .all()
    )
    pop_names = {int(p.metacluster_id): p.name for p in pops}

    sample_info = [
        {
            "sample_index": s.sample_index,
            "sample_label": s.sample_label,
            "group": s.group,
            "batch": s.batch,
            "covariates": s.covariates or {},
            "n_events_used": int(s.n_events_used or 0),
        }
        for s in samples
    ]
    totals = {int(s.sample_index): int(s.n_events_used or 0) for s in samples}

    counts: dict[int, dict[int, int]] = {}
    medians: dict[int, dict[int, dict]] = {}
    markers: set[str] = set()
    mc_ids: set[int] = set()
    for st in stats:
        mc = int(st.metacluster_id)
        si = int(st.sample_index)
        mc_ids.add(mc)
        counts.setdefault(mc, {})[si] = int(st.cell_count)
        me = st.median_expression or {}
        medians.setdefault(mc, {})[si] = dict(me)
        markers.update(me.keys())

    return {
        "samples": sample_info,
        "metacluster_ids": sorted(mc_ids),
        "pop_names": pop_names,
        "counts": counts,
        "totals": totals,
        "medians": medians,
        "markers": sorted(markers),
    }
