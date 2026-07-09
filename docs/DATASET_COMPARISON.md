# Spectral test datasets — evaluation of the two candidates you found

You pointed at two candidate datasets, both advertised as having mixed+unmixed
pairs. I fetched and inspected both from their canonical sources. Summary
verdict up front:

- **Phitonex "above-and-beyond-40" (40-colour Cytek Aurora)** — a genuine,
  verified matched mixed+unmixed pair with a FlowJo workspace. **Downloaded and
  verified.** The catch is its license: **CC BY-ND (NoDerivatives)**.
- **AutoSpectral 40-colour ID7000 (Mendeley)** — permissively licensed
  (**CC BY 4.0**), but the pieces are split across three Mendeley records and
  the raw FCS live inside a single **~10 GB zip**. Not "small," and the
  convenient record holds only analysis scaffolding, not FCS.

## 1. Phitonex — `Phitonex/above-and-beyond-40` (GitHub)

**What it is.** A 40-colour immunophenotyping panel (34 commercial conjugates +
6 NovaFluor drop-ins) on human cells, acquired on a **5-laser Cytek Aurora**
(serial U0363, 28-Feb-2020). The repo ships **98 FCS files (~1.5 GB)**:
`data/raw/` (raw detector signal) and `data/unmixed/` (SpectroFlo-unmixed),
plus single-colour reference controls and beads, and a **FlowJo `.wsp`
workspace**.

**Verified matched pair (downloaded here).** The fully-stained "E1 all 40
colours" sample:

| File | Events × ch | Meaning |
|------|-------------|---------|
| `PBMC_40color_E1_MIXED_raw.fcs` | 132,360 × 71 | Raw detectors (UV1–16, V, B, YG, R across 5 lasers) |
| `PBMC_40color_E1_UNMIXED.fcs` | 132,360 × 47 | Per-fluorophore (BUV395, LIVE/DEAD Blue, BUV496 …) + scatter |
| `40color_FlowJo_workspace.wsp` | — | Real FlowJo workspace over these files |

Identical event count + identical instrument keywords on both files confirm they
are the *same acquisition* before and after unmixing. The unmixing here is
**vendor (SpectroFlo) ground truth**, not a reconstruction — which is exactly
what you want to validate a tool's own unmixing against. The bundled `.wsp` also
makes this the natural fixture for the proposal's **FlowJo-interop
demonstration** (open our output in FlowJo; read their gates via GatingML/wsp).

**License caveat — CC BY-ND 4.0.** The repo's `LICENSE.md` is Creative Commons
**Attribution-NoDerivatives**. That is fine for *using the data as an input*
(running it through the tool, publishing results with attribution), but the
"NoDerivatives" clause is a real constraint if we wanted to **redistribute a
modified/derived copy** of the FCS files as part of our repo (e.g. a
down-sampled or re-annotated version). Safe uses: link to it, cite it, use it as
a test input, ship results. Not safe: commit an edited copy into our
open-source repo as "our" bundled test data. (I am not a lawyer — this is the
license text's plain reading; confirm with counsel before redistribution.)

## 2. AutoSpectral 40-colour ID7000 (Mendeley Data)

**What it is.** The dataset behind the AutoSpectral unmixing work (a 2025
bioRxiv preprint, accession 2025.10.27.684855, per web search — not
independently verified here). Human PBMC from buffy coats, a 40-colour panel,
acquired on a **5-laser Sony ID7000** — so this is the ID7000 counterpart to the
Aurora dataset above. It provides multiple unmixing variants of the same data
(WLSM = Sony software; WLS / scAF / perCellFluor = AutoSpectral variants), which
is genuinely useful for comparing unmixing approaches.

**License.** The Mendeley record is **CC BY 4.0** — permissive, *derivatives
allowed*. Better than phitonex for redistribution.

**The practical problems.** The AutoSpectral data are spread across ≥3 Mendeley
DOIs, and they don't cleanly separate into a small "mixed + unmixed pair":

| Mendeley DOI | Holds | Size |
|--------------|-------|------|
| `10.17632/2kvc98hc65.2` (the link you had) | FlowJo `.wsp`, R script, control CSVs, slides — **no FCS** | 1.3 MB |
| `10.17632/y2zp5xx2hg.2` (raw/original) | a **single ~10 GB `.zip`** | 9,964 MB |
| `10.17632/vzdxy8n7wf.1` (AutoSpectral unmixed) | `.wsp`, R script, control CSVs — **no loose FCS** | 3.1 MB |

So the record you linked contains only the analysis scaffolding; the actual FCS
are inside a ~10 GB archive on a different DOI. Retrievable, but not "small," and
extracting a clean matched pair means downloading and unpacking 10 GB first.

## Recommendation

For a **small, permissively-licensed, redistributable** bundle we can commit to
our own repo, the `flowSpecs` dataset already saved in `../dataset/` remains the
best fit (Artistic-2.0, ~3 MB, mixed + unmixed + controls).

For a **large, high-fidelity, vendor-ground-truth** fixture with a real FlowJo
workspace — the right thing for the unmixing-accuracy and FlowJo-interop
demonstrations — use the **phitonex E1 pair** (downloaded here), *as an
external input we cite rather than redistribute-modified*, respecting CC BY-ND.

If a permissive license on a **large** dataset is the priority, the AutoSpectral
ID7000 data (CC BY 4.0) is the one to pursue — but budget for the 10 GB raw
download and an unzip step, and confirm which files inside form the matched
pair.

## Provenance notes / corrections

- The phitonex files are **Cytek Aurora**, not Sony ID7000. The ID7000 is the
  *separate* AutoSpectral dataset. (The two were easy to conflate from the
  descriptions.)
- All instrument/provenance facts above (`$CYT`, `$CYTSN`, `$DATE`, `$PAR`,
  event counts) were read directly from the FCS keyword blocks of the files I
  downloaded, not from dataset descriptions.
- I did not verify the specific staining-panel antecedents (which prior panel /
  OMIP each deposit builds on); the phitonex page cites a prior panel as
  footnote "[1]" but I did not resolve that reference. Treat panel-lineage
  claims as unconfirmed until checked against each deposit's own documentation.
