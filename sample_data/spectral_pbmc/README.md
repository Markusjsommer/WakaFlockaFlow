# Spectral flow cytometry test dataset (PBMC, Cytek Aurora)

A small, real spectral dataset for developing and demonstrating the proposed
analysis tool. It exercises **both** the tool's v1 path (unmixed FCS in) and the
v2 path (unmix raw detector data using single-stain controls).

## Provenance

- **Source:** the `fullPanel` and `unmixCtrls` example objects shipped in the
  Bioconductor package **flowSpecs** (author: Jakob Theorell), obtained from the
  package's public GitHub repository (`jtheorell/flowSpecs`, `data/*.rda`).
- **Instrument:** Cytek Aurora (5-laser), serial **R0066**, acquired
  **25-Oct-2018**, 47 parameters. These provenance fields (`$CYT`, `$CYTSN`,
  `$DATE`, `$PAR`) were read directly from the original FCS keyword block.
- **Biology:** human PBMC, a ~12-marker immunophenotyping panel
  (CD3, CD4, CD8a, CD14, CD19, CD56, CD11c, CD41b, CD45RA, IgM, a PE marker,
  and a viability dye), plus bead-based single-stain controls.
- The fully-stained sample here is an 8,000-event subsample of the original
  407,824 events (`$TOT` in the source keywords), which keeps the dataset small
  while preserving population structure.

## License

flowSpecs is distributed under **Artistic-2.0** (an OSI-approved permissive
license). The bundled example data ships with the package under the same terms.
This makes the dataset safe to redistribute inside an open-source project,
consistent with the project's licensing requirement. Cite Theorell et al. /
the flowSpecs package if used in a publication.

## Files

| File | Events × channels | Role |
|------|-------------------|------|
| `PBMC_spectral_MIXED_raw.fcs` | 8,000 × 47 | **Mixed** — raw detector signal (V1–V16, B1–B16, R1–R10 + scatter). Instrument export *before* unmixing. Input to the v2 "unmix in app" path. |
| `PBMC_spectral_UNMIXED.fcs` | 8,000 × 18 | **Unmixed** — per-marker abundances (CD3, CD4, …) + scatter. Input to the v1 "analysis only" path. |
| `single_stain_controls/*.fcs` | 500 × 47 (×15) | Single-stain bead + cell controls. Reference spectra needed to build the unmixing matrix. |
| `QC_biology_check.png` | — | QC figure: scatter cleanup, CD3/CD19 lineage split, CD4/CD8 T-cell split. |

## How the unmixed file was produced

The `PBMC_spectral_UNMIXED.fcs` file was **derived here**, not taken from a
vendor unmixer, so the mixed→unmixed relationship is fully reproducible:

1. For each single-stain control, subtract the unstained-bead autofluorescence
   baseline and take the median of the positive population (top 30 % by total
   signal) across all 42 fluorescence detectors → one peak-normalised
   **spectral signature** per fluorophore.
2. Add an autofluorescence endmember from the unstained PBMC control.
3. Stack the 13 signatures into a 42 × 13 spectrum matrix **S** and solve the
   per-event linear unmixing `A = X · pinv(S)ᵀ` (ordinary least squares — the
   transparent form of the weighted-least-squares approach Cytek uses).

**Validity check.** In the unmixed data, CD3 (T cells) and CD19 (B cells) are
decorrelated (r ≈ −0.03, as expected for mutually exclusive lineages), while
CD3 and CD8a correlate positively (r ≈ +0.23, the CD8 T-cell subset). Each
fluorophore's signature peaks at a distinct detector spread across all three
lasers.

## Suggested uses (maps to the proposal's impact demonstrations)

- **Concordance-at-speed:** automated gating / clustering (FlowSOM, openCyto) on
  the unmixed file vs. a manual gate hierarchy.
- **Unmixing demo (v2):** rebuild the unmixing from the raw file + controls and
  compare to the provided unmixed file.
- **QC / transform:** arcsinh transform selection, scatter cleanup, doublet and
  viability gating on real Aurora-scale values (max ~4.19e6).

## Note on network access

An alternative candidate — FlowRepository **FR-FCM-Z2QV** (titled "40 color OMIP
new donors unmixed", primary researcher Joanne Lannigan, per the FlowRepository
experiment page) — was identified but requires a FlowRepository login to
download and the site is
currently rate-limiting downloads, so it was not used. FlowRepository's TLS
certificate is also expired (a known server-side issue). The flowSpecs data
gives an equivalent mixed+unmixed Aurora workflow under a clean permissive
license with no login.
