# WakaFlakaFlow — Product Requirements Document

*Integrated v2 — Layers 1–4 with Amendment A applied.*
*Amendment A fixes: (1) FlowJo .wsp export in ExportBundle, (2) openCyto hierarchical*
*gating mode (GatingTemplate entity + 10 API endpoints + Section 3.6 params),*
*(3) Python↔R subprocess IPC protocol (Section 2.5), (4) Tauri desktop packaging (Section 4.6).*

---

## Table of Contents

1. Layer 1 — UI/UX Specification
2. Layer 2 — API & Data Model Specification (incl. §2.5 IPC Protocol)
3. Layer 3 — Algorithm Parameter Defaults (incl. §3.6 OpenCyto)
4. Layer 4 — Dependency Versions (incl. §4.6 Tauri Desktop)

---

# PRD Supplement: Layer 1 — UI/UX Specification

*Informed by competitive analysis of FlowJo, FCS Express, Kaluza, OMIQ, and open-source ecosystems.
All user requirements incorporated: dashboard-centric layout, real-time job progress panel,
hover tooltips + click-to-drill-down, and collapsible beginner tutorial sidebar.*

---

## 1.0 Design Principles (Derived from Competitive Gap Analysis)

| Competitor pain point | Our design response |
|----------------------|---------------------|
| Gate → report gap: results require manual export to Excel/Prism | Pipeline dashboard drives the user from QC to report in one continuous flow; export bundle generated in one click |
| No contextual interpretation: tools show numbers, not meaning | Every metric card and result table has a hover tooltip explaining what the value means and what action to take |
| Steep learning curve: tools don't adapt to novice vs expert | Collapsible guided tutorial sidebar; progressive disclosure (advanced params hidden behind "Advanced" toggle) |
| Gating UX is frustrating (OMIQ user quote) | Gate editor is a dedicated full-screen interface, not a pop-up; undo/redo stack; real-time event count feedback while drawing |
| No AI-assisted gating in mainstream tools | FlowSOM auto-gating result shown first; human review and correction layered on top |
| Collaboration requires cloud upload (OMIQ) | Shareable export bundle; no cloud required; reproducible R script included |

---

## 1.1 Application Shell

### Global Layout (always present)
```
┌─────────────────────────────────────────────────────────────┐
│  [logo] CytoFlow Studio          [Session: PBMC_2025-07-09] │  ← Top nav bar (48px)
├──┬──────────────────────────────────────────────────────────┤
│  │                                                          │
│  │           PAGE CONTENT (varies by route)                 │
│  │                                                          │
│  │                                                          │
│[?]│                                                          │  ← Tutorial button (sidebar)
└──┴──────────────────────────────────────────────────────────┘
```

**Top navigation bar** (48px fixed height, dark background):
- Left: application logo + name
- Center: current session name (editable inline on double-click)
- Right: pipeline step indicator (5 dots: QC → Transform → Batch → Cluster → Analyze) — filled dot = complete, pulsing dot = in progress, empty dot = not started

**Tutorial sidebar button**:
- Fixed position: bottom-left corner, 40×40px circular button
- Icon: lightbulb (💡); changes to ✕ when panel is open
- On click: slides in a 320px panel from the left edge, overlaying (not pushing) page content
- Tutorial panel content: context-aware — shows guidance relevant to the current page (e.g., on the Gate Editor page, shows "How to draw a polygon gate")
- Panel has sections: Quick Start / Current Step Guide / Glossary / Video Links (placeholder)

---

## 1.2 Page Routing

```
/                         → Home (session list)
/sessions/:id             → Session Dashboard  ← primary working screen
/sessions/:id/qc          → QC Detail
/sessions/:id/gate-editor → Gate Editor (full-screen)
/sessions/:id/diff        → Differential Analysis Results
/sessions/:id/export      → Export
```

No navigation bar between pages — users return via breadcrumb in top nav or "Back to Dashboard" button.

---

## 1.3 Home Page — Session List

**Layout**: centered card grid, max 3 columns.

Each session card (280×160px) shows:
- Session name (bold, 16px)
- Last updated timestamp
- Pipeline status strip (5 colored segments, green = done, grey = pending)
- File count badge

**Actions**:
- Click card → navigate to `/sessions/:id` (Session Dashboard)
- "+ New Session" button (top right, primary color): creates session and navigates immediately
- Hover card → shows "Delete" icon (top-right corner of card); confirmation modal before delete

---

## 1.4 Session Dashboard — Primary Screen

### Overall Layout Philosophy
The dashboard is **radial-from-center**: the most important visualization occupies the center panel; all supporting information panels surround it. Clicking any panel navigates to a full-screen detail view.

```
┌────────────────────────────────────────────────────────────────────┐
│  Pipeline:  [QC ✓]──[Transform ✓]──[Batch ●]──[Cluster ○]──[Diff ○]  │
├──────────────┬─────────────────────────────┬───────────────────────┤
│              │                             │                       │
│  FILE LIST   │     CENTER PANEL            │   POPULATION TREE     │
│  PANEL       │   (primary visualization)   │   PANEL               │
│  (left)      │                             │   (right)             │
│              │                             │                       │
├──────────────┼─────────────────────────────┼───────────────────────┤
│  QC SUMMARY  │   JOB PROGRESS PANEL        │   QUICK STATS         │
│  PANEL       │   (bottom center)           │   PANEL               │
│  (btm left)  │                             │   (btm right)         │
└──────────────┴─────────────────────────────┴───────────────────────┘
```

### Center Panel — Primary Visualization
**Content** (changes based on pipeline stage):
- Before clustering: UMAP placeholder with message "Run clustering to see cell populations"
- After clustering: UMAP scatter plot colored by metacluster, rendered with WebGL (supports 1M+ events at 60fps)
- After gating: UMAP colored by named population (user-assigned colors)

**Interactions**:
- Scroll to zoom; drag to pan
- Hover event point → tooltip: population name, metacluster ID
- Click a cluster region → highlights corresponding row in Population Tree panel
- Toolbar overlay (top-right of panel): [Channel X selector] [Channel Y selector] [Color by: metacluster / marker] [Download PNG]

**Click panel header** → navigates to Gate Editor full-screen page.

### Left Panel — File List
**Dimensions**: 240px wide, full height of panel row.

**Content**: scrollable list of uploaded FCS files, one row per file.

Each row shows:
- Filename (truncated to 28 chars with tooltip for full name)
- Event count badge (e.g., "245k")
- QC status icon: ✓ green (passed) / ⚠ yellow (flagged, removal >20%) / ✕ red (failed, removal >70%)
- Batch label pill (colored chip, e.g., "Batch A")

**Hover row** → tooltip shows: acquisition date, channel count, removal rate (e.g., "PeacoQC removed 8.3% of events").

**Click row** → highlights that file's events in the center scatter plot (other files dimmed to 20% opacity).

**Panel footer**: "+ Upload Files" button → opens file upload drawer.

**Click panel header "Files"** → stays on dashboard (no drill-down; file management is inline).

### Right Panel — Population Tree
**Dimensions**: 260px wide.

**Content**: collapsible tree of named cell populations.

Each node row shows:
- Colored dot (population color) + population name
- Cell count + percentage of parent (e.g., "12,400 · 23.5%")
- Lock icon if population has a confirmed gate

**Hover node** → tooltip shows: median expression of top 3 markers, gate type (FlowSOM auto / manual polygon / etc.)

**Click node** → highlights that population's events in the center scatter plot; other populations dimmed.

**Double-click node name** → inline rename (text input, Enter to confirm).

**Right-click node** → context menu:
- "Edit Gate" → opens Gate Editor
- "Set Color" → color picker
- "Add Child Population" → creates sub-population
- "Delete" → confirmation modal

**Panel header "Populations"** → click navigates to Gate Editor.

### Bottom-Center Panel — Job Progress
**Dimensions**: full center column width, 140px height.

**Content**: displays current and recent jobs.

If a job is running:
```
[●] Running: FlowSOM Clustering (nClus=10)
    ████████████░░░░░░░░  65%   Training SOM epoch 7/10
    Started 2 min ago · Estimated: ~1 min remaining
    [Cancel]
```

If no job is running:
```
[✓] Last job: QC completed 5 min ago (8 files processed, 1 flagged)
    [View QC Report]          [Run Next Step: Batch Correction →]
```

**Progress bar**: animated fill, color changes: grey (pending) → blue pulsing (running) → green (complete) → red (failed).

**Step message** updates in real-time from `Job.message` field (polled every 2 seconds).

**"Run Next Step" button**: automatically identifies the next uncompleted pipeline step and pre-fills sensible defaults.

**Hover panel** → no tooltip (progress is self-explanatory). **Click panel** → expands to show full job history log (last 10 jobs, each with timestamp and outcome).

### Bottom-Left Panel — QC Summary
**Dimensions**: 240px wide, 140px height.

**Content** (before QC): "QC not yet run. Click to configure and run."

**Content** (after QC): 3 metric cards side by side:

```
┌──────────┬──────────┬──────────┐
│  8/8     │  1       │  avg 6.2%│
│  Files   │  Flagged │  Removal │
│  passed  │  ⚠       │  rate    │
└──────────┴──────────┴──────────┘
```

**Hover each metric card** → tooltip:
- "Files passed": "All 8 files passed PeacoQC quality thresholds (removal rate < 70%)"
- "Flagged": "1 file had >20% event removal. Review recommended before proceeding."
- "Removal rate": "Average percentage of events removed across all files. Typical range: 1–15%."

**Click panel** → navigates to `/sessions/:id/qc` (QC Detail page).

### Bottom-Right Panel — Quick Stats
**Dimensions**: 260px wide, 140px height.

**Content**: 4 stats displayed as large numbers with labels:

```
┌────────┬────────┬────────┬────────┐
│ 1.24M  │  8     │  10    │  0.23  │
│ Total  │ Files  │ Popul- │ Mean   │
│ Cells  │        │ ations │ EMD↓   │
└────────┴────────┴────────┴────────┘
```
(Mean EMD↓ = batch correction improvement; shown only after batch correction runs)

**Hover each stat** → tooltip explaining the metric.

**Click panel** → no navigation (informational only); panel briefly highlights on click with a gentle pulse animation.

---

## 1.5 QC Detail Page — `/sessions/:id/qc`

**Layout**: two-column.

**Left column** (360px): file list with QC metrics table.

| File | Events | Removed | Rate | Status |
|------|--------|---------|------|--------|
| PBMC_01.fcs | 245,000 | 20,300 | 8.3% | ✓ |
| PBMC_02.fcs | 198,000 | 51,480 | 26.0% | ⚠ |

Click a row → right column updates to show that file's QC visualization.

**Right column**: QC visualization for selected file.
- Top: event time-series plot (X = acquisition time, Y = event count per bin); removed bins shown in red
- Bottom: per-channel signal stability plots (one sparkline per channel; flagged channels highlighted)
- "Re-run QC with custom parameters" button → opens parameter drawer (all PeacoQC params exposed with Layer 3 defaults pre-filled and labeled with source: "Default from Emmaneel et al. 2021")

**Action bar** (bottom): "Accept QC Results & Proceed" → marks QC as complete, returns to dashboard.

---

## 1.6 Gate Editor — `/sessions/:id/gate-editor`

**Layout**: full-screen, two-panel.

```
┌─────────────────────────────────────┬────────────────────────┐
│                                     │  Population Tree       │
│      SCATTER PLOT CANVAS            │  (same as dashboard,   │
│      (WebGL, full-screen)           │   260px wide)          │
│                                     │                        │
│                                     ├────────────────────────┤
│                                     │  Gate Inspector        │
│                                     │  (current gate params) │
└─────────────────────────────────────┴────────────────────────┘
```

**Scatter plot canvas interactions**:
- Channel selector dropdowns (X and Y axes): searchable, shows marker name + channel name
- Gate drawing toolbar (left edge, vertical):
  - Polygon tool (default): click to add vertices, double-click to close
  - Rectangle tool: click-drag
  - Ellipse tool: click-drag from center
  - Selection tool: click existing gate to select/resize/move
  - Eraser: delete selected gate
- While drawing: live event count shown in top-right corner of canvas ("12,400 events inside gate — 23.5% of parent")
- Undo/redo: Cmd+Z / Cmd+Shift+Z; up to 20 steps
- Color scale legend (bottom-right): shows current color mapping

**Gate Inspector** (right panel, bottom section):
- Shows gate type, vertex coordinates (editable numerically), and event count
- "Name this population" text field
- "Confirm Gate" button → saves gate and re-counts events
- "Export GatingML" button → downloads gate as GatingML 2.0 XML

**Tutorial sidebar content on this page**: step-by-step guide "How to gate CD4+ T cells from a lymphocyte scatter plot."

---

## 1.7 Differential Analysis Results Page — `/sessions/:id/diff`

**Layout**: tab-based, two tabs: "Differential Abundance (DA)" and "Differential State (DS)".

**DA tab**:
- Top: volcano plot (X = log fold change, Y = -log10 adjusted p-value); significant populations highlighted in red; hover point → tooltip with population name, LFC, p-adj
- Bottom: sortable table (population name, cell count per group, LFC, p-value, p-adj, significant ✓/—)
- Table row hover → highlights corresponding point on volcano plot

**DS tab**:
- Heatmap: rows = significant marker+population combinations, columns = samples, cells = median expression (z-scored); color scale: blue–white–red
- Below heatmap: same sortable table structure

**Action bar**: "Download DA Results (CSV)" / "Download DS Results (CSV)" / "Back to Dashboard"

---

## 1.8 Export Page — `/sessions/:id/export`

**Layout**: single-column, centered (max 640px width).

**Content**: checklist of bundle contents (all checked by default):
- [✓] Original FCS files
- [✓] Post-QC FCS files
- [✓] Panel definition (CSV)
- [✓] QC report (HTML)
- [✓] Gating strategy (GatingML 2.0 XML)
- [✓] Clustering results (populations.csv + UMAP coordinates.parquet)
- [✓] Differential analysis results (DA.csv + DS.csv)
- [✓] Reproducible R script (reproduce.R)
- [✓] Software version log (session_info.txt)

Below checklist: estimated bundle size (shown as "~1.2 GB including raw FCS / ~45 MB without").

"Generate Export Bundle" button → triggers export job; progress shown inline (same polling pattern).

On completion: "Download Bundle (.zip)" button appears.

**Sharing note** (info box): "Share the .zip file with collaborators. They can re-run the full analysis using the included reproduce.R script on any machine with R ≥ 4.4 installed."

---

## 1.9 Interaction Patterns — Global Rules

### Hover Tooltip Standard
- **Trigger**: 400ms hover delay (prevents tooltip flicker during mouse movement)
- **Content**: always three lines: (1) metric name in bold, (2) plain-language explanation, (3) recommended action if applicable
- **Position**: above the element by default; flips below if near top edge
- **Style**: dark background (#1a1a1a), white text, 12px, max 280px wide, 4px border-radius
- **Dismiss**: immediately on mouse-out

### Click-to-Drill-Down Standard
- Panel headers are always clickable (underlined on hover, cursor: pointer)
- Navigation is always push (browser back button works)
- Current page breadcrumb shown in top nav: "Session Dashboard > QC Detail"

### Loading States
- Skeleton screens (grey animated shimmer) for panels waiting on data — never blank white
- Job progress panel is the single source of truth for async task state; no other spinners

### Error States
- Failed jobs: Job Progress panel turns red, shows error message from `Job.error` field
- "Retry" button always shown for failed jobs
- File upload errors: inline error under the failed filename, with specific message (e.g., "File is not a valid FCS 3.1 format")

### Empty States
- Every panel that can be empty has an illustrated placeholder with a one-line prompt and a CTA button
- Example: Population Tree when no clustering run exists → icon + "No populations yet. Run FlowSOM clustering to see cell populations." + [Run Clustering] button

---

## 1.10 Visual Design Tokens

| Token | Value | Usage |
|-------|-------|-------|
| `--color-primary` | `#2563EB` | Primary buttons, active pipeline step |
| `--color-success` | `#16A34A` | Completed steps, passed QC |
| `--color-warning` | `#D97706` | Flagged QC, removal rate >20% |
| `--color-danger` | `#DC2626` | Failed jobs, removal >70%, significant DA hits |
| `--color-surface` | `#F8FAFC` | Page background |
| `--color-panel` | `#FFFFFF` | Panel card background |
| `--color-border` | `#E2E8F0` | Panel borders, dividers |
| `--color-text-primary` | `#0F172A` | Headlines, labels |
| `--color-text-secondary` | `#64748B` | Metadata, tooltips |
| `--font-size-xl` | `24px` | Panel stat numbers |
| `--font-size-base` | `14px` | Body text |
| `--font-size-sm` | `12px` | Badges, tooltips |
| `--border-radius-panel` | `8px` | All panel cards |
| `--shadow-panel` | `0 1px 3px rgba(0,0,0,0.1)` | Panel card shadow |
| `--transition-standard` | `150ms ease` | Hover states, panel expansion |

**Font**: Inter (system fallback: -apple-system, sans-serif)

**Scatter plot color palette** (population colors, colorblind-safe, 10 colors):
`#E64B35, #4DBBD5, #00A087, #3C5488, #F39B7F, #8491B4, #91D1C2, #DC0000, #7E6148, #B09C85`

---

## 1.11 Responsive Behavior

Target viewport: **≥ 1280px width** (lab workstations and laptops).
Below 1280px: side panels collapse to icon-only mode; clicking icon expands as overlay.
Below 900px: show "Viewport too narrow" banner (flow cytometry analysis is not a mobile task).

---

*Document version: 2025-07 | Design inputs: competitive analysis of FlowJo, FCS Express, Kaluza, OMIQ, open-source R/Python ecosystem; user requirements: dashboard-centric layout, real-time job progress panel, hover tooltips + click drill-down, collapsible beginner tutorial sidebar*


---

# PRD Supplement: Layer 2 — API & Data Model Specification

*Architecture decisions: single-user, polling-based job status, single Celery queue, data sharing via export bundle.*

---

## 2.1 Core Entity Model

All persistent state is derived from 12 entities. The dependency graph flows top-to-bottom; nothing below can exist without what is above it.

```
Session
  ├── FCSFile
  │     └── QCResult
  ├── Panel
  ├── TransformConfig
  ├── BatchCorrectionRun
  ├── ClusteringRun
  │     └── Population (self-referencing tree)
  │           └── GateDefinition
  ├── DiffAnalysisRun
  ├── ExportBundle          ← primary data-sharing mechanism
  └── Job                  ← transient; tracks async task progress
```

### Entity Definitions

#### `Session`
The top-level container for a single analysis project.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `name` | string | NOT NULL, max 255 | User-defined label |
| `description` | string | nullable | |
| `status` | enum | `draft` / `in_progress` / `complete` | Derived from pipeline step completion |
| `created_at` | datetime | NOT NULL | |
| `updated_at` | datetime | NOT NULL | Auto-updated on any child change |

#### `FCSFile`
One uploaded `.fcs` file. Metadata parsed from FCS header on upload.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `session_id` | UUID | FK → Session, NOT NULL | |
| `filename` | string | NOT NULL | Original filename |
| `file_path` | string | NOT NULL | Absolute path inside container volume |
| `n_events` | integer | NOT NULL | Total event count from `$TOT` |
| `n_channels` | integer | NOT NULL | From `$PAR` |
| `acquisition_date` | date | nullable | From `$DATE` header |
| `batch_label` | string | nullable | User-assigned batch identifier for CytoNorm |
| `is_reference` | boolean | default FALSE | Marks reference samples for CytoNorm training |
| `qc_status` | enum | `pending` / `passed` / `flagged` / `failed` | Updated after QC run |
| `uploaded_at` | datetime | NOT NULL | |

#### `Panel`
Channel-to-marker mapping for a session. One panel per session; channels listed as rows.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `session_id` | UUID | FK → Session, UNIQUE | One panel per session |
| `channels` | JSON array | NOT NULL | See `PanelChannel` schema below |
| `updated_at` | datetime | NOT NULL | |

**`PanelChannel` object** (element of `channels` array):
```json
{
  "channel_name": "BV421-A",
  "marker_name": "CD19",
  "fluorochrome": "BV421",
  "marker_type": "cell_type",
  "include_in_clustering": true
}
```
`marker_type`: `"cell_type"` (used for clustering) | `"cell_state"` (used for DS testing) | `"scatter"` (excluded from analysis)

#### `TransformConfig`
Transform settings for a session. Applied uniformly to all files.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `session_id` | UUID | FK → Session, UNIQUE | One config per session |
| `method` | enum | `logicle` / `arcsinh` | |
| `params` | JSON object | NOT NULL | See transform param schemas below |
| `updated_at` | datetime | NOT NULL | |

**Logicle params object**:
```json
{ "T": 262144, "M": 4.5, "W": 0.5, "A": 0, "auto_estimate_W": true }
```
**Arcsinh params object**:
```json
{ "cofactor": 5 }
```

#### `QCResult`
PeacoQC output; one record per FCS file per QC run.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `fcs_file_id` | UUID | FK → FCSFile, NOT NULL | |
| `job_id` | UUID | FK → Job | |
| `removal_rate` | float | 0.0–1.0 | Fraction of events removed |
| `flagged` | boolean | NOT NULL | TRUE if removal_rate > 0.20 |
| `channel_flags` | JSON object | nullable | `{"BV421-A": "monotonic_increase"}` |
| `removed_indices_path` | string | nullable | Path to binary file of removed event indices |
| `params_used` | JSON object | NOT NULL | Snapshot of PeacoQC params at time of run |
| `created_at` | datetime | NOT NULL | |

#### `BatchCorrectionRun`
One CytoNorm run for a session.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `session_id` | UUID | FK → Session, NOT NULL | |
| `job_id` | UUID | FK → Job | |
| `reference_file_ids` | JSON array | NOT NULL | UUIDs of FCSFiles used as reference |
| `params` | JSON object | NOT NULL | `{"nClus": 25, "nQ": 101, "seed": 42}` |
| `emd_before` | float | nullable | Mean Earth Mover's Distance before correction |
| `emd_after` | float | nullable | Mean EMD after correction |
| `model_path` | string | nullable | Path to saved CytoNorm model (rds file) |
| `status` | enum | `pending`/`running`/`completed`/`failed` | |
| `created_at` | datetime | NOT NULL | |

#### `ClusteringRun`
One FlowSOM run. Multiple runs per session allowed (parameter exploration).

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `session_id` | UUID | FK → Session, NOT NULL | |
| `job_id` | UUID | FK → Job | |
| `label` | string | nullable | User-assigned run label, e.g. "nClus=15 exploration" |
| `params` | JSON object | NOT NULL | `{"xdim":10,"ydim":10,"nClus":10,"rlen":10,"seed":42}` |
| `n_cells_trained` | integer | nullable | Actual cells used for SOM training |
| `umap_path` | string | nullable | Path to Parquet file of UMAP coordinates |
| `status` | enum | `pending`/`running`/`completed`/`failed` | |
| `created_at` | datetime | NOT NULL | |
| `is_active` | boolean | default FALSE | Only one active run drives downstream steps |


#### `GatingTemplate`

A named, reusable hierarchical gating strategy (openCyto mode). Defines the ordered
sequence of gates applied uniformly to all FCS files in a session.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `session_id` | UUID | FK → Session, NOT NULL | |
| `name` | string | NOT NULL | e.g. "PBMC Lymphocyte Panel v2" |
| `description` | string | nullable | |
| `source` | enum | `manual` / `imported_flowjo` | `imported_flowjo` = parsed from .wsp via CytoML |
| `nodes` | JSON array | NOT NULL | Ordered list of `GatingNode` objects (see schema below) |
| `created_at` | datetime | NOT NULL | |
| `updated_at` | datetime | NOT NULL | |

**`GatingNode` object** (element of `nodes` array):
```json
{
  "node_id": "lymphocytes",
  "parent_node_id": null,
  "population_name": "Lymphocytes",
  "algorithm": "mindensity",
  "x_channel": "FSC-A",
  "y_channel": "SSC-A",
  "params": {"gate_range": [0.01, 0.99]}
}
```

Supported `algorithm` values: `mindensity`, `gate_mindensity`, `flowClust.2d`,
`quantileGate`, `rectangleGate`, `polygonGate`. See Section 3.6 for parameters.

---

#### `TemplateGatingRun`

One execution of a `GatingTemplate` across all FCS files in a session.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `session_id` | UUID | FK → Session, NOT NULL | |
| `template_id` | UUID | FK → GatingTemplate, NOT NULL | |
| `job_id` | UUID | FK → Job | |
| `label` | string | nullable | User-assigned run label |
| `status` | enum | `pending`/`running`/`completed`/`failed` | |
| `is_active` | boolean | default FALSE | Only one active run per session drives downstream |
| `created_at` | datetime | NOT NULL | |

---

#### `Population`
A named cell cluster or gated sub-population. Forms a tree (root populations have no parent).

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `clustering_run_id` | UUID | FK → ClusteringRun, **nullable** | Source if FlowSOM clustering | |
| `parent_id` | UUID | FK → Population (self), nullable | NULL = root population |
| `name` | string | NOT NULL | User-assigned, e.g. "CD4+ T cells" |
| `som_node_ids` | JSON array | nullable | FlowSOM node IDs assigned to this population |
| `template_gating_run_id` | UUID | FK → TemplateGatingRun, nullable | Source if openCyto template |
  | `metacluster_id` | integer | nullable | FlowSOM metacluster index |
| `cell_count` | integer | NOT NULL | Absolute event count |
| `percentage_of_parent` | float | NOT NULL | Relative to parent (or total if root) |
| `median_expression` | JSON object | NOT NULL | `{"CD19": 1234.5, "CD3": 89.2, ...}` |
| `color` | string | default `"#AAAAAA"` | Hex color for UI display |
| `is_manual_gate` | boolean | default FALSE | TRUE if defined by user gate rather than FlowSOM |

#### `GateDefinition`
The geometric or boolean definition of a manually drawn gate.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `population_id` | UUID | FK → Population, UNIQUE | One gate per population |
| `gate_type` | enum | `polygon` / `ellipse` / `range` / `boolean` | |
| `x_channel` | string | nullable | Channel name on X axis |
| `y_channel` | string | nullable | Channel name on Y axis (NULL for range gate) |
| `coordinates` | JSON object | NOT NULL | See gate coordinate schemas below |
| `gatingml_xml` | text | nullable | GatingML 2.0 serialization for export |
| `created_at` | datetime | NOT NULL | |
| `updated_at` | datetime | NOT NULL | |

**Coordinate schemas by gate type**:
```json
// polygon
{ "vertices": [[x1,y1],[x2,y2],...] }

// ellipse
{ "center": [cx,cy], "semi_axes": [a,b], "angle_deg": 45.0 }

// range (1D)
{ "min": 100.0, "max": 5000.0 }

// boolean
{ "operator": "AND", "operands": ["pop_uuid_1", "pop_uuid_2"] }
```

#### `DiffAnalysisRun`
One diffcyt run. Multiple runs per session allowed.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `session_id` | UUID | FK → Session, NOT NULL | |
| `clustering_run_id` | UUID | FK → ClusteringRun, **nullable** | Source if FlowSOM clustering | |
| `job_id` | UUID | FK → Job | |
| `method_da` | enum | `edgeR` / `GLMM` | |
| `method_ds` | enum | `limma` / `LMM` | |
| `group_variable` | string | NOT NULL | Column name in sample metadata used as grouping factor |
| `random_effect_variable` | string | nullable | e.g. `"patient_id"` for GLMM/LMM |
| `params` | JSON object | NOT NULL | Full parameter snapshot |
| `result_da_path` | string | nullable | Path to DA results Parquet |
| `result_ds_path` | string | nullable | Path to DS results Parquet |
| `status` | enum | `pending`/`running`/`completed`/`failed` | |
| `created_at` | datetime | NOT NULL | |

#### `ExportBundle`
A shareable, reproducible analysis archive. This is the primary data-sharing mechanism.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `session_id` | UUID | FK → Session, NOT NULL | |
| `job_id` | UUID | FK → Job | |
| `bundle_path` | string | nullable | Path to `.zip` file inside container volume |
| `bundle_size_bytes` | integer | nullable | |
| `manifest` | JSON object | NOT NULL | Lists what is included; see schema below |
| `created_at` | datetime | NOT NULL | |

**Bundle manifest schema**:
```json
{
  "includes_raw_fcs": true,
  "includes_processed_fcs": true,
  "includes_panel": true,
  "includes_qc_report": true,
  "includes_gating_strategy_gatingml": true,
  "includes_gating_strategy_wsp": true,
  "includes_clustering_results": true,
  "includes_diff_analysis": true,
  "includes_r_session_info": true,
  "includes_reproducibility_script": true,
  "flowsom_params": {"xdim": 10, "ydim": 10, "nClus": 10},
  "software_versions": {
    "flowkit": "1.3.2",
    "FlowSOM": "2.20.0",
    "PeacoQC": "1.12.0",
    "CytoML": "3.14.0"
  }
}
```

**Bundle `.zip` contents**:
```
bundle_<session_id>_<date>/
  ├── raw_fcs/                  # original uploaded files
  ├── processed_fcs/            # post-QC, post-transform files
  ├── panel.csv
  ├── qc_report.html
  ├── gating_strategy.xml       # GatingML 2.0 — machine-readable, open standard
  ├── gating_strategy.wsp          # FlowJo workspace — opens directly in FlowJo
  ├── clustering/
  │   ├── flowsom_model.rds
  │   ├── populations.csv       # name, cell_count, percentage, median_expression
  │   └── umap_coordinates.parquet
  ├── diff_analysis/
  │   ├── DA_results.csv
  │   └── DS_results.csv
  ├── reproduce.R               # self-contained R script to re-run full analysis
  └── session_info.txt          # R sessionInfo() + Python pip freeze
```

#### `Job`
Tracks every async background task. Polled by the frontend every 2 seconds.

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| `id` | UUID | PK | |
| `type` | enum | `qc` / `batch_correction` / `clustering` / `diff_analysis` / `export` | |
| `status` | enum | `pending` / `running` / `completed` / `failed` | |
| `progress` | integer | 0–100 | Percentage complete |
| `message` | string | nullable | Current step description, e.g. "Training FlowSOM (epoch 7/10)" |
| `error` | string | nullable | Error message if failed |
| `result` | JSON object | nullable | Summary result on completion |
| `created_at` | datetime | NOT NULL | |
| `updated_at` | datetime | NOT NULL | Auto-updated on every status change |
| `completed_at` | datetime | nullable | |

---

## 2.2 Database

**Selection: SQLite (v1) → PostgreSQL (v2 multi-user upgrade path)**

Rationale:
- Single-user local Docker deployment has no concurrent write contention
- SQLite requires no separate database container; one file inside the volume
- All ORM code uses SQLAlchemy 2.0 (dialect-agnostic); switching to PostgreSQL requires only changing `DB_URL`
- File paths stored in the DB are container-internal paths; the volume mount makes them accessible

**SQLite pragmas** (set at connection time):
```sql
PRAGMA journal_mode = WAL;      -- allows concurrent reads during writes
PRAGMA foreign_keys = ON;       -- enforce FK integrity
PRAGMA synchronous = NORMAL;    -- safe + faster than FULL for local use
```

**Upgrade path note**: When upgrading to multi-user (v2), add `owner_id UUID NOT NULL` to `Session` and `Job`, add a `User` table, and add a `WHERE owner_id = ?` clause to all queries. No other schema changes required.

---

## 2.3 REST API Design

**Base URL**: `http://localhost:8000/api/v1`

**Conventions**:
- All request/response bodies: `application/json`
- File uploads: `multipart/form-data`
- File downloads: `application/octet-stream`
- Timestamps: ISO 8601 UTC (`2025-07-09T14:32:00Z`)
- IDs: UUID v4 strings
- Errors: `{"error": "message", "detail": {...}}` with appropriate HTTP status code
- Long-running operations: return `{"job_id": "uuid"}` immediately; poll `GET /jobs/{job_id}`

---

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/sessions` | List all sessions (newest first) |
| `POST` | `/sessions` | Create a new session |
| `GET` | `/sessions/{session_id}` | Get session details including pipeline status |
| `PATCH` | `/sessions/{session_id}` | Update name or description |
| `DELETE` | `/sessions/{session_id}` | Delete session and all child data |

**`POST /sessions` request body**:
```json
{ "name": "PBMC Panel Run 2025-07-09", "description": "Healthy donor cohort" }
```

**`GET /sessions/{id}` response**:
```json
{
  "id": "uuid",
  "name": "PBMC Panel Run 2025-07-09",
  "status": "in_progress",
  "pipeline_status": {
    "files_uploaded": true,
    "panel_defined": true,
    "qc_complete": true,
    "transform_configured": true,
    "batch_correction_complete": false,
    "clustering_complete": false,
    "diff_analysis_complete": false
  },
  "created_at": "2025-07-09T14:00:00Z",
  "updated_at": "2025-07-09T14:32:00Z"
}
```

---

### FCS Files

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions/{session_id}/files` | Upload one or more FCS files (multipart) |
| `GET` | `/sessions/{session_id}/files` | List all files with QC status |
| `GET` | `/sessions/{session_id}/files/{file_id}` | File details + parsed FCS header metadata |
| `PATCH` | `/sessions/{session_id}/files/{file_id}` | Set `batch_label`, `is_reference` |
| `DELETE` | `/sessions/{session_id}/files/{file_id}` | Remove file |
| `GET` | `/sessions/{session_id}/files/{file_id}/events` | Sampled events for scatter plot rendering |

**`POST /sessions/{id}/files` request**: `multipart/form-data`, field name `files[]`, accepts multiple files.

**`GET /sessions/{id}/files/{file_id}/events` query params**:
- `x_channel` (required): channel name for X axis
- `y_channel` (required): channel name for Y axis
- `max_events` (optional, default 50000): downsample for rendering
- `post_qc` (optional, default true): exclude QC-removed events

**`GET .../events` response**:
```json
{
  "x_channel": "BV421-A",
  "y_channel": "PE-A",
  "n_total": 245000,
  "n_returned": 50000,
  "events": [[x1,y1],[x2,y2],...]
}
```

---

### Panel

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/sessions/{session_id}/panel` | Get panel definition |
| `PUT` | `/sessions/{session_id}/panel` | Set or replace panel definition |
| `GET` | `/sessions/{session_id}/panel/template` | Auto-generate panel template from FCS channel names |

**`PUT /sessions/{id}/panel` request body**:
```json
{
  "channels": [
    {"channel_name": "BV421-A", "marker_name": "CD19", "fluorochrome": "BV421",
     "marker_type": "cell_type", "include_in_clustering": true},
    {"channel_name": "FSC-A", "marker_name": "FSC", "fluorochrome": null,
     "marker_type": "scatter", "include_in_clustering": false}
  ]
}
```

---

### Transform Configuration

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/sessions/{session_id}/transform` | Get current transform config |
| `PUT` | `/sessions/{session_id}/transform` | Set transform config |

**`PUT /sessions/{id}/transform` request body** (logicle example):
```json
{
  "method": "logicle",
  "params": {"T": 262144, "M": 4.5, "W": 0.5, "A": 0, "auto_estimate_W": true}
}
```

---

### Quality Control

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions/{session_id}/qc` | Trigger QC run on all files → returns `job_id` |
| `GET` | `/sessions/{session_id}/qc` | Get QC results for all files |
| `GET` | `/sessions/{session_id}/qc/{file_id}` | QC result for one file |

**`POST /sessions/{id}/qc` request body** (params optional; defaults used if omitted):
```json
{
  "params": {
    "IT_limit": 0.6, "MAD": 6, "consecutive_bins": 5,
    "min_cells": 150, "max_bins": 500, "remove_zeros": false
  }
}
```

**`POST /sessions/{id}/qc` response**:
```json
{ "job_id": "uuid" }
```

---

### Batch Correction

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions/{session_id}/batch-correction` | Trigger CytoNorm run → returns `job_id` |
| `GET` | `/sessions/{session_id}/batch-correction` | Get latest batch correction result |

**`POST /sessions/{id}/batch-correction` request body**:
```json
{
  "reference_file_ids": ["uuid1", "uuid2"],
  "params": {"nClus": 25, "nQ": 101, "seed": 42}
}
```

---

### Clustering

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions/{session_id}/clustering` | Trigger FlowSOM run → returns `job_id` |
| `GET` | `/sessions/{session_id}/clustering` | List all clustering runs |
| `GET` | `/sessions/{session_id}/clustering/{run_id}` | Get run details |
| `PATCH` | `/sessions/{session_id}/clustering/{run_id}` | Set `is_active = true` (activates this run) |

**`POST /sessions/{id}/clustering` request body**:
```json
{
  "label": "nClus=15 exploration",
  "params": {"xdim": 10, "ydim": 10, "nClus": 10, "rlen": 10, "seed": 42}
}
```

---

### Populations & Gates

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/sessions/{session_id}/clustering/{run_id}/populations` | List all populations (tree structure) |
| `GET` | `/sessions/{session_id}/clustering/{run_id}/populations/{pop_id}` | Single population details |
| `PATCH` | `/sessions/{session_id}/clustering/{run_id}/populations/{pop_id}` | Rename, recolor population |
| `PUT` | `/sessions/{session_id}/clustering/{run_id}/populations/{pop_id}/gate` | Set or update gate definition |
| `POST` | `/sessions/{session_id}/clustering/{run_id}/populations/{pop_id}/gate/apply` | Re-apply gate → recount cells |

**`GET .../populations` response** (tree structure):
```json
[
  {
    "id": "uuid",
    "name": "CD4+ T cells",
    "cell_count": 12400,
    "percentage_of_parent": 23.5,
    "color": "#E64B35",
    "metacluster_id": 3,
    "median_expression": {"CD3": 2345.1, "CD4": 8901.3, "CD8": 45.2},
    "children": [
      {
        "id": "uuid",
        "name": "Naive CD4+",
        "cell_count": 4200,
        "percentage_of_parent": 33.9,
        ...
      }
    ]
  }
]
```

**`PUT .../gate` request body** (polygon example):
```json
{
  "gate_type": "polygon",
  "x_channel": "FSC-A",
  "y_channel": "SSC-A",
  "coordinates": {"vertices": [[1000,500],[2000,500],[2000,1500],[1000,1500]]}
}
```

---


### Gating Templates

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions/{session_id}/gating-templates` | Create template manually |
| `POST` | `/sessions/{session_id}/gating-templates/import` | Import from FlowJo `.wsp` file |
| `GET` | `/sessions/{session_id}/gating-templates` | List all templates |
| `GET` | `/sessions/{session_id}/gating-templates/{template_id}` | Get template with all nodes |
| `PUT` | `/sessions/{session_id}/gating-templates/{template_id}` | Replace template |
| `DELETE` | `/sessions/{session_id}/gating-templates/{template_id}` | Delete template |
| `POST` | `/sessions/{session_id}/gating-templates/{template_id}/run` | Execute template → returns `job_id` |
| `GET` | `/sessions/{session_id}/template-gating-runs` | List all template gating runs |
| `GET` | `/sessions/{session_id}/template-gating-runs/{run_id}` | Get run details |
| `PATCH` | `/sessions/{session_id}/template-gating-runs/{run_id}` | Set `is_active = true` |

**`POST /sessions/{id}/gating-templates/import` request**: `multipart/form-data`, field
`wsp_file`. The R subprocess calls CytoML to parse the .wsp gate hierarchy into the
`GatingNode` array format automatically.

**`POST .../run` response**: `{ "job_id": "uuid" }`

---

### Differential Analysis

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions/{session_id}/diff-analysis` | Trigger diffcyt run → returns `job_id` |
| `GET` | `/sessions/{session_id}/diff-analysis` | List all runs |
| `GET` | `/sessions/{session_id}/diff-analysis/{run_id}` | Get results |
| `GET` | `/sessions/{session_id}/diff-analysis/{run_id}/download` | Download results as CSV |

**`POST /sessions/{id}/diff-analysis` request body**:
```json
{
  "clustering_run_id": "uuid",
  "method_da": "edgeR",
  "method_ds": "limma",
  "group_variable": "condition",
  "random_effect_variable": null
}
```

**`GET .../diff-analysis/{run_id}` response** (results inline for small result sets):
```json
{
  "id": "uuid",
  "status": "completed",
  "da_results": [
    {
      "population_id": "uuid",
      "population_name": "CD4+ T cells",
      "log_fold_change": 1.23,
      "p_value": 0.004,
      "p_adj": 0.021,
      "significant": true
    }
  ],
  "ds_results": [
    {
      "population_id": "uuid",
      "population_name": "CD4+ T cells",
      "marker": "CD25",
      "log_fold_change": 0.87,
      "p_value": 0.011,
      "p_adj": 0.044,
      "significant": true
    }
  ]
}
```

---

### Export (Data Sharing)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/sessions/{session_id}/export` | Create export bundle → returns `job_id` |
| `GET` | `/sessions/{session_id}/export` | List all export bundles |
| `GET` | `/sessions/{session_id}/export/{bundle_id}/download` | Download `.zip` bundle |

**`POST /sessions/{id}/export` request body**:
```json
{
  "clustering_run_id": "uuid",
  "diff_analysis_run_id": "uuid",
  "options": {
    "include_raw_fcs": true,
    "include_processed_fcs": true,
    "include_reproducibility_script": true
  }
}
```

---

### Jobs (Polling)

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/jobs/{job_id}` | Get current job status |

**`GET /jobs/{job_id}` response**:
```json
{
  "id": "uuid",
  "type": "clustering",
  "status": "running",
  "progress": 65,
  "message": "Training FlowSOM SOM (epoch 7/10)",
  "error": null,
  "result": null,
  "created_at": "2025-07-09T14:30:00Z",
  "updated_at": "2025-07-09T14:31:42Z"
}
```

On completion (`status = "completed"`), `result` contains a summary:
```json
{
  "status": "completed",
  "progress": 100,
  "message": "Clustering complete",
  "result": {
    "clustering_run_id": "uuid",
    "n_metaclusters": 10,
    "n_cells_total": 1245000
  }
}
```

**Frontend polling contract**: Poll every **2 seconds** while `status` is `pending` or `running`. Stop polling when `status` is `completed` or `failed`.

---

## 2.4 Full Workflow Sequence (Happy Path)

```
1. POST /sessions                          → session_id
2. POST /sessions/{id}/files              → file_ids
3. PATCH /sessions/{id}/files/{id}        → set batch_label, is_reference
4. GET  /sessions/{id}/panel/template     → pre-filled panel
5. PUT  /sessions/{id}/panel              → confirm channel assignments
6. PUT  /sessions/{id}/transform          → set logicle/arcsinh params
7. POST /sessions/{id}/qc                 → job_id → poll → QC results
8. POST /sessions/{id}/batch-correction   → job_id → poll → correction model
9. POST /sessions/{id}/clustering         → job_id → poll → populations tree
10. PATCH .../populations/{id}            → rename clusters (human review)
11. PUT .../populations/{id}/gate         → draw gate on scatter plot
12. POST /sessions/{id}/diff-analysis     → job_id → poll → DA/DS results
13. POST /sessions/{id}/export            → job_id → poll → download .zip
```

---


---

## 2.5 Python↔R Subprocess Communication Protocol

All R-backed computations (PeacoQC, CytoNorm, FlowSOM, openCyto, diffcyt) use a
**file-based IPC protocol** over a job-scoped working directory. No `rpy2` linking.

### Directory Layout

```
/data/jobs/{job_id}/
  ├── input/
  │   ├── events.parquet        # transformed, QC-filtered event matrix (cells × channels)
  │   ├── params.json           # algorithm parameters (Layer 3 defaults + user overrides)
  │   ├── metadata.json         # panel, sample info, file list
  │   └── (additional per-job inputs — see table below)
  ├── output/                   # R writes here; Python reads after completion
  │   ├── result.parquet        # primary output data
  │   ├── result_metadata.json  # summary stats + completion signal
  │   └── progress.json         # updated each epoch/step for live UI progress
  └── error.json                # written by R on unrecoverable error
```

Python polls for `output/result_metadata.json` or `error.json` every **5 seconds**.

### Job-Specific I/O

| Job type | Additional inputs | Key outputs |
|----------|------------------|-------------|
| `qc` | `raw_events.parquet` | `removed_indices.parquet`, `qc_flags.json` |
| `batch_correction` | `reference_events.parquet`, `target_events.parquet` | `corrected_events.parquet`, `cytonorm_model.rds`, `emd_stats.json` |
| `clustering` | `events.parquet` | `cluster_assignments.parquet`, `som_model.rds`, `umap_coords.parquet` |
| `template_gating` | `events.parquet`, `template.json` | `gate_assignments.parquet`, `gate_diagnostics.json` |
| `diff_analysis` | `events.parquet`, `cluster_assignments.parquet`, `sample_groups.json` | `da_results.parquet`, `ds_results.parquet` |

### Key Schemas

**`params.json`** (common fields):
```json
{
  "job_type": "clustering",
  "job_id": "uuid",
  "r_seed": 42,
  "channels_to_use": ["BV421-A", "PE-A", "APC-A"],
  "algorithm_params": {"xdim": 10, "ydim": 10, "nClus": 10, "rlen": 10}
}
```

**`result_metadata.json`** (signals completion to Python):
```json
{
  "job_type": "clustering",
  "status": "completed",
  "wall_time_seconds": 42.3,
  "n_cells_processed": 1245000,
  "summary": {"n_metaclusters": 10}
}
```

**`error.json`**:
```json
{
  "status": "failed",
  "error_message": "FlowSOM: insufficient cells for nClus=25",
  "r_traceback": "Error in ...",
  "suggestion": "Reduce nClus or increase min_cells_per_cluster"
}
```

**`progress.json`** (read by Python every 5s → updates `Job.progress` + `Job.message`):
```json
{ "progress": 65, "message": "Training FlowSOM SOM (epoch 7/10)" }
```

### R Script Entry Points

```
backend/r_scripts/
  ├── run_peacoqc.R
  ├── run_cytonorm.R
  ├── run_flowsom.R
  ├── run_opencyto.R
  └── run_diffcyt.R
```

Python invocation:
```python
subprocess.run(
    ["Rscript", "--vanilla", f"backend/r_scripts/run_{job_type}.R",
     "--job-dir", f"/data/jobs/{job_id}"],
    capture_output=True,
    timeout=3600
)
```

R scripts read all configuration from `input/params.json`; they receive no other arguments.
On job completion, Python copies output files to permanent storage and deletes the job
working directory.

---

*Document version: 2025-07 | Architecture decisions: single-user (no auth), polling
interval 2s, single Celery queue, SQLite v1 → PostgreSQL v2, export bundle as primary
sharing mechanism, file-based IPC for Python↔R subprocess boundary*



---

# PRD Supplement: Layer 3 (Algorithm Parameter Defaults) & Layer 4 (Dependency Versions)

*All parameters sourced from primary literature full text or official package documentation.*

---

## Layer 3: Algorithm Parameter Defaults

### 3.1 Data Transformation

#### Logicle Transform (default for fluorescence flow cytometry)
| Parameter | Default | Description | Source |
|-----------|---------|-------------|--------|
| T | 262,144 | Instrument top-of-scale value (18-bit ADC full range) | Moore & Parks 2012, Cytometry A; cytopy docs |
| M | 4.5 | Total display width in decades | Moore & Parks 2012: "M=4.5 is generally suitable for all fluorescence measurements" |
| W | 0.5 | Linearization width near zero | flowCore default; Parks et al. 2006 |
| A | 0 | Additional negative range in decades | Moore & Parks 2012 default |

> **Note**: W is the most important tuning parameter — increase it when heavy compensation produces many negative events. flowCore's `estimateLogicle()` can auto-estimate the optimal W from data.

#### Arcsinh Transform (default for mass cytometry / CyTOF)
| Parameter | Default | Description | Source |
|-----------|---------|-------------|--------|
| cofactor | 5 | Used in `asinh(x / cofactor)`; controls width of linear region | diffcyt package docs (Bioconductor v1.28.0): "Default = 5, appropriate for mass cytometry (CyTOF) data" |
| cofactor (fluorescence FC) | 150–500 | Larger cofactor recommended for fluorescence FC | diffcyt package docs note |

> **Implementation note**: In v1, auto-detect data type from FCS metadata (`$DATATYPE` field and channel count). Apply Logicle by default for fluorescence FC; apply Arcsinh (cofactor=5) for mass cytometry.

---

### 3.2 Quality Control — PeacoQC Parameters

**Source**: Emmaneel et al. 2021, *Cytometry A*, PMID:34549881 (full text extracted directly)

| Parameter | Default | Meaning | Adjustment |
|-----------|---------|---------|------------|
| `IT_limit` | **0.6** | Isolation tree gain threshold; controls stringency of anomalous bin detection | Lower → stricter (removes more); higher → more lenient |
| `MAD` | **6** | Median absolute deviation multiplier; detects single-channel signal drift | Lower → stricter |
| `consecutive_bins` | **5** | Minimum retained bins between removed regions; prevents isolated small segments from being kept | Higher → stricter |
| `min_cells` | **150** | Minimum cell count per bin | Reduce for small samples |
| `max_bins` | **500** | Maximum number of bins | — |
| `remove_zeros` | FALSE (flow) / TRUE (mass cytometry) | Whether to remove zero values before bin evaluation | Must be TRUE for mass cytometry data |

**Warning thresholds** (logged to QC report automatically; sample is not deleted):
- Removal rate > **70%**: flag as potential data quality issue or parameter misconfiguration
- Removal rate > **20%**: auto-generate visualization for manual review
- Any channel with monotonically increasing or decreasing trend: flag as possible signal drift

**Validated scope**: Same default parameters validated across conventional flow, mass cytometry, and spectral flow cytometry (16 FlowRepository datasets).

---

### 3.3 Batch Correction — CytoNorm Parameters

**Source**: Van Gassen et al. 2019, *Cytometry A*, PMID:31633883 (full text extracted directly)

| Parameter | Recommended value | Meaning | Source detail |
|-----------|-------------------|---------|---------------|
| FlowSOM grid (internal) | **10×10** | SOM grid size used for clustering reference samples | Paper validated: CV < 2 typically holds for ≤ 25–30 metaclusters |
| `nClus` (metaclusters) | **25** (≤ 30 markers) | Final metacluster count; CV rises sharply beyond 30 | Paper Fig. 4: "CV > 2 occurs for 30 or more clusters" |
| `nQ` (quantile count) | **101** | Quantiles (0, 0.01, …, 1) describing each cluster × marker distribution | Methods: 101 quantiles outperforms 2-quantile linear approach |
| Goal distribution | Mean quantiles across all batches | Normalization target | Default; a specific batch can also be set as target |
| Spline type | Monotone Hermite spline (`monoH.FC`) | Prevents artifacts during extrapolation | R `stats::splinefun` |
| Extrapolation anchors | (0, 0) and (8, 8) | Prevents erroneous transformations at boundaries | Paper methods section |

**Training subsample** (large datasets):
- Total cell count used for SOM training across **all pooled reference samples**: **1,000,000 cells** (paper: "a random subset was selected from each sample to use for training (1 million cells in total)")
- Per-sample contribution ≈ 1,000,000 ÷ number of reference samples; e.g. with 10 reference samples, each contributes ~100,000 cells
- Events beyond the total cap are mapped to existing SOM nodes and do not participate in training

**Key constraints** (must be surfaced in UI):
- Reference samples must span the **complete expression range** of the target samples (paper Fig. 7: insufficient training coverage causes incorrect normalization)
- Recommended: use **two reference samples** — one for training, one for blind validation
- Validation metric: Earth Mover's Distance (EMD); mean EMD reduction after correction ≈ 61% (±39%)

---

### 3.4 Clustering — FlowSOM Parameters

**Source**: FlowSOM Bioconductor official documentation v2.20.0 (2026-03-17) + Python FlowSOM docs

| Parameter | Default | Meaning | Recommended range |
|-----------|---------|---------|-------------------|
| `xdim` | **10** | SOM grid X dimension | 8–15 (12–15 for high-parameter panels) |
| `ydim` | **10** | SOM grid Y dimension | Same as above |
| `nClus` | **10** | Metacluster count (final cell population count) | User-specified; UI should offer presets: 5 / 10 / 15 / 20 / 25 |
| `rlen` | **10** (default) | SOM training iterations; larger = more stable but slower | 100–140 recommended for CyTOF data (Frontiers Immunol 2024) |
| `seed` | Must be set explicitly | Ensures reproducibility | Fix at 42 or make user-configurable |
| `transformFunction` | `logicleTransform()` | Built-in transform; set to NULL if data already pre-processed | — |

**Metacluster count selection logic** (write into UI tooltip):
1. If user does not specify, run `nClus=10` for a fast initial result
2. Provide an "auto-select" option: run `maxMeta=20`, find optimal k via Consensus clustering
3. When used within CytoNorm workflow, metacluster count must be < 30 (batch effects contaminate clustering beyond this)

---

### 3.5 Differential Testing — diffcyt Parameters

**Source**: diffcyt Bioconductor documentation v1.28.0

| Test type | Default method | Use case |
|-----------|---------------|----------|
| Differential abundance (DA) | **`diffcyt-DA-edgeR`** | Simple two-group comparison; no random effects |
| Differential abundance (DA, paired/longitudinal) | `diffcyt-DA-GLMM` | Contains random effects such as patient ID |
| Differential state (DS) | **`diffcyt-DS-limma`** | Marker expression differences within cell populations |
| Differential state (with random effects) | `diffcyt-DS-LMM` | DS testing with random effects |

**Method selection logic** (write into UI decision tree):
```
Paired samples or repeated measurements?
  ├── No  → DA: edgeR;  DS: limma  (default, computationally fast)
  └── Yes → DA: GLMM;  DS: LMM    (include patient_id as random effect)
```

**Arcsinh transform parameters** (diffcyt internal):
- If input data already transformed: `transform=FALSE`
- If input is raw data: `transform=TRUE`, `cofactor=5` (CyTOF) or user-specified

**Marker classification requirement** (user must configure):
- `cell_type` markers: used for clustering to define cell populations
- `cell_state` markers: used for DS testing (typically functional markers)
- UI must provide a drag-and-drop assignment interface

---


---

### 3.6 Hierarchical Gating — OpenCyto Algorithm Parameters

**Source**: openCyto Bioconductor documentation v2.14+ and flowDensity vignette

| Algorithm | Parameter | Default | Description |
|-----------|-----------|---------|-------------|
| `mindensity` | `gate_range` | `[0.01, 0.99]` | Quantile range to search for density valley |
| `mindensity` | `min` | auto | Lower bound of search range (auto-estimated from data) |
| `mindensity` | `max` | auto | Upper bound of search range |
| `flowClust.2d` | `K` | `2` | Number of mixture components (2 = signal + background) |
| `flowClust.2d` | `quantile` | `0.95` | Quantile of mixture component used as gate boundary |
| `flowClust.2d` | `trans` | `0` | Internal transform (0 = pre-transformed input) |
| `quantileGate` | `probs` | `0.95` | Percentile threshold (0.95 = top 5% excluded) |

**Template execution order**: nodes applied in order of `nodes` array; parent must precede child.

**Fallback behavior**: if an algorithm fails on a specific file, gate is placed at the
`gate_range` midpoint and the population is flagged `auto_gate_failed = true`. Users see
⚠ in the Population Tree and are prompted to adjust manually.

**Import fidelity from FlowJo .wsp**: rectangle and polygon gates import with 100%
fidelity (coordinates preserved exactly); ellipse gates map to `flowClust.2d`;
quadrant gates decompose into 4 child populations.

## Layer 4: Dependency Version Specifications

### 4.1 Python Backend

**Minimum runtime**: Python ≥ 3.10 (FlowKit explicitly supports 3.10–3.14)

#### Core Python Dependencies
| Package | Version | Purpose | Source |
|---------|---------|---------|--------|
| `flowkit` | **1.3.2** (current latest) | FCS read/write, GatingML 2.0, FlowJo .wsp parsing | PyPI (released late 2025; NumPy 2+ support added in 1.3.0) |
| `fastapi` | ≥ 0.111 | REST API backend framework | — |
| `uvicorn` | ≥ 0.30 | ASGI server | — |
| `celery` | ≥ 5.3 | Async task queue for long-running jobs | — |
| `redis` | ≥ 5.0 | Celery broker | — |
| `numpy` | ≥ 2.0 | Numerical computing | FlowKit 1.3.x supports NumPy 2 |
| `pandas` | ≥ 2.0 | Tabular data processing | — |
| `scipy` | ≤ 1.16.0 | Statistical computing (upper bound due to statsmodels constraint) | scanpy release notes |
| `umap-learn` | ≥ 0.5 | UMAP dimensionality reduction for visualization | — |
| `anndata` | ≥ 0.10 | Single-cell data structure (interoperable with FlowKit) | FlowKit docs recommendation |
| `sqlalchemy` | ≥ 2.0 | Provenance database ORM | — |
| `pydantic` | ≥ 2.0 | API data validation | — |
| `pyarrow` | ≥ 14.0 | Feather/Parquet export | FlowKit 1.3.x new dependency |

**Notes**:
- FlowKit's FlowUtils component uses C extensions; pre-built wheels available for most platforms. Apple Silicon users should upgrade pip first.
- `scipy ≤ 1.16.0` constraint comes from scanpy (statsmodels compatibility issue, confirmed 2025).

#### Optional Python Dependencies (not needed when calling R via subprocess)
If `rpy2` direct binding is chosen (requires legal review of AGPL chain):
| Package | Version | Note |
|---------|---------|------|
| `rpy2` | ≥ 3.5 | Python–R bridge |

---

### 4.2 R Backend (Subprocess Layer)

**Minimum runtime**: R ≥ 4.4 (required by Bioconductor 3.20+)

#### R / Bioconductor Packages
| Package | Version | Purpose | Install | License |
|---------|---------|---------|---------|---------|
| `FlowSOM` | **2.20.0** (Bioc 3.21, 2026-03-17) | Primary clustering engine | `BiocManager::install("FlowSOM")` | GPL ≥ 2 |
| `flowCore` | ≥ 2.14 | FCS file I/O, transforms | Bioconductor | Artistic-2.0 |
| `flowWorkspace` | ≥ 4.14 | GatingML and FlowJo workspace R I/O | Bioconductor | LGPL |
| `openCyto` | ≥ 2.14 | Template-based hierarchical gating | Bioconductor | **AGPL-3.0** |
| `CytoNorm` | ≥ 1.12 | Batch correction | GitHub: saeyslab/CytoNorm | **GPL ≥ 2** |
| `PeacoQC` | ≥ 1.12 | Quality control | Bioconductor | **GPL ≥ 3** |
| `diffcyt` | **1.28.0** (Bioc 3.21) | Differential abundance/state testing | Bioconductor | MIT |
| `cyCombine` | ≥ 1.8 | Batch integration (no reference samples needed) | Bioconductor | MIT |
| `CytoML` | ≥ 3.14 | Cross-platform gating data conversion | Bioconductor | **AGPL-3.0** |
| `limma` | ≥ 3.58 | DS testing statistical backend | Bioconductor | LGPL |
| `edgeR` | ≥ 4.0 | DA testing statistical backend | Bioconductor | LGPL |

**License risk summary** (consistent with proposal analysis):
- **AGPL-3.0**: openCyto, CytoML → source code must be disclosed if service is provided over a network
- **GPL ≥ 2**: FlowSOM, CytoNorm → derivative works must be released under the same license
- **MIT / Artistic-2.0**: diffcyt, cyCombine, flowCore → permissive; no copyleft obligation

---

### 4.3 Frontend

| Technology | Version | Notes |
|-----------|---------|-------|
| Node.js | ≥ 20 LTS | Frontend build environment |
| React | ≥ 18 | SPA framework |
| Vite | ≥ 5 | Build tool |
| WebGL / deck.gl or regl-scatter2d | Current stable | GPU-accelerated scatter plot rendering for millions of cell events |

---

### 4.4 Containerized Deployment Specifications

#### Dockerfile Base Image Strategy
```
# Backend (recommended two-layer image)
Base:   python:3.12-slim-bookworm
R layer: r-base:4.4.x  (or rocker/r-ver:4.4)

# Minimum hardware requirements (single-user local deployment)
RAM:   ≥ 16 GB  (1M cells × 30 markers requires ~8–12 GB)
CPU:   ≥ 4 cores
Disk:  ≥ 50 GB  (R environment + packages ≈ 5 GB; data cache on demand)
GPU:   Not required  (frontend WebGL rendering uses client-side GPU)

# Facility-level multi-user deployment (recommended)
RAM:   ≥ 64 GB
CPU:   ≥ 16 cores
Disk:  ≥ 500 GB (SSD)
```

#### Core Environment Variables (define in docker-compose.yml)
```yaml
REDIS_URL:                 redis://redis:6379/0
DB_URL:                    sqlite:///./provenance.db   # single-user; switch to postgres for multi-user
MAX_EVENTS_PER_FILE:       5000000
DEFAULT_FLOWSOM_XDIM:      10
DEFAULT_FLOWSOM_YDIM:      10
DEFAULT_FLOWSOM_NCLUS:     10
DEFAULT_PEACOQC_IT_LIMIT:  0.6
DEFAULT_PEACOQC_MAD:       6
R_LIBS_USER:               /usr/local/lib/R/library
```

---

### 4.5 Version Pinning Strategy

1. **Python**: maintain `requirements.txt` + `requirements-lock.txt` (generated by pip-compile)
2. **R**: maintain `renv.lock` (renv package management), locking Bioconductor release version numbers
3. **Container images**: push to private registry and pin by SHA digest rather than tag
4. **Update cadence**: quarterly dependency review; run regression tests in staging environment before updating lock files

---

*Document version: 2025-07 | Layer 3 parameter sources: PeacoQC full text (PMID:34549881), CytoNorm full text (PMID:31633883), diffcyt official docs (Bioc v1.28.0), FlowSOM official docs (v2.20.0), logicle transform original specification (Moore & Parks 2012) | Layer 4 version sources: PyPI, Bioconductor release pages, queried July 2025*
---

### 4.6 Alternative Deployment: Desktop App (Tauri) — Phase 3

*Addresses the proposal's "one-click/one-command deployment" goal for single-scientist
use; no Docker required.*

**Technology**: [Tauri](https://tauri.app/) v2 (Rust-based native shell). Bundles
Python backend + R environment + frontend into a single installable:
`.app` (macOS), `.exe` (Windows), `.deb`/`.AppImage` (Linux).

```
User experience:
  Double-click CytoFlowStudio.app
    → Tauri shell starts bundled Python/FastAPI server (localhost:8000)
    → Tauri shell starts bundled Redis instance
    → Default browser opens to http://localhost:8000
    → No terminal, no Docker required
```

| | Docker (facility, Phase 1) | Tauri (desktop, Phase 3) |
|--|---------------------------|--------------------------|
| Deploy | `docker compose up` | Double-click installer |
| Multi-user | Yes (v2 upgrade) | Single-user only |
| Data location | Docker volume | `~/CytoFlowStudio/data/` |
| R environment | Bundled in container | Portable renv snapshot |
| Update path | `docker compose pull` | Tauri auto-updater |

**Backend code sharing**: 100% identical — only the shell/packaging layer differs.

**R bundling**: ship portable R binary (Rtools portable on Windows; R.app framework on
macOS) + pre-built `renv` library snapshot. R subprocess path set to bundled binary at runtime.

