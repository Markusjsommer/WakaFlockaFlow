# Validation

Three independent checks: the differential engine fires on real signal, stays
silent on none, and reproduces a published result on data we did not design.

## 1. Positive + negative control (synthetic, known ground truth)

A synthetic cohort with a *planted* difference (a CD8 T-cell subpopulation
enriched in the treated group, ~14% → ~38%, and CD45RA raised within it). See
[`scripts/make_differential_demo.py`](../scripts/make_differential_demo.py) and
[`sample_data/differential_demo/`](../sample_data/differential_demo/).

- **Positive (diffcyt / edgeR + limma):** the planted CD8 lineage is recovered as
  the top differential-abundance hit (Naive CD8 T cell log2FC **+1.08**,
  p_adj **3.8e-15**; CD8 T cell **+1.56**, p_adj 6.2e-8), and the planted CD45RA
  state shift is the top differential-state marker in that population
  (log2FC **+3.73**, p_adj **3.4e-9**).
- **Negative:** on a no-difference cohort (identical samples), the same pipeline
  returns **zero significant hits** (all p = 1.0). No false positives.

## 2. Operating characteristic (effect-size sweep)

Same generator, varying the planted enrichment, 4 vs 4, Python rank-test engine:

| Enrichment | Top +log2FC (population) | p_adj | Significant populations |
|---|---|---|---|
| **0% (null)** | +0.03 (noise) | 0.69 | **0** |
| 5% | +0.14 (Naive CD8 T) | 0.088 | 0 |
| 15% | +0.37 (Naive CD8 T) | 0.034 | 5 |
| 30% | +0.66 (Naive CD8 T) | 0.035 | 5 |

The null returns nothing; the CD8 effect size scales monotonically with the
planted signal; detection begins around a 15% shift. (The Python engine floors at
p ≈ 0.03 for 4 vs 4; diffcyt is more powerful where R is available.)

## 3. Reproduction on real, published data (Bodenmiller BCR-XL)

The **Bodenmiller BCR-XL** dataset (16 samples, B-cell-receptor / FcεRI
crosslinking vs unstimulated) is the reference benchmark for diffcyt, with
independently hand-gated populations. We ran it end to end through the tool
(FCS → joint FlowSOM + UMAP → differential, diffcyt engine), contrasting
Reference vs BCR-XL.

In the **CD20⁺ B-cell population** (auto-named after the CD20 annotation fix
below), phospho-signaling rises under BCR-XL stimulation:

| Marker | log2FC (BCR-XL vs Reference) | p_adj |
|---|---|---|
| **pS6** | **+0.70** | **1.2e-6** |
| pPlcg2 | +0.19 | 4.6e-4 |
| pErk | +0.08 | 2.4e-3 |
| pAkt | +0.16 | 8.1e-3 |
| pZap70 | +0.01 | 2.7e-2 |

This is the canonical B-cell-receptor signaling response reported by Bodenmiller
et al. (2012) and used as the diffcyt benchmark — recovered on data the tool did
not design, with correct markers, correct direction, and small adjusted p-values.

**Honest caveats:**
- Bodenmiller BCR-XL is **mass cytometry (CyTOF)**, not spectral flow — the same
  analysis engine, a different instrument.
- Clustering ran on all markers (including phospho), so a few populations are
  state-defined and shift in abundance between groups; the clean
  differential-state result above is the CD20⁺ B-cell cluster.
- The tool's B-cell auto-naming originally required CD19; this panel carries CD20
  instead. We added a CD20-anchored B-cell signature (see
  [`backend/analysis/annotate.py`](../backend/analysis/annotate.py)), after which
  the CD20⁺ clusters auto-name as "B cell".

## Reproduce

- Synthetic controls + sweep: `./.venv/bin/python scripts/make_differential_demo.py`,
  then run the cohort + differential in the app (the `differential_demo/` set ships).
- Bodenmiller: in the Docker image (R present), install `HDCytoData`, export
  `Bodenmiller_BCR_XL_flowSet()` to FCS, load as a cohort tagged Reference vs
  BCR-XL, and run the differential (diffcyt engine).

## One-paragraph summary (for a writeup)

On a synthetic cohort with known ground truth, the tool recovers the planted CD8
enrichment (p_adj 3.8e-15) and CD45RA state shift (p_adj 3.4e-9) and returns zero
hits on a matched null; an effect-size sweep shows detection scaling with signal
and no false positives at zero effect. On the published Bodenmiller BCR-XL
benchmark — real, independently hand-gated data the tool did not design — it
reproduces the known B-cell-receptor signaling response (pS6 up in CD20⁺ B cells
under stimulation, p_adj 1.2e-6).
