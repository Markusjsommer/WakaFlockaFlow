#!/usr/bin/env Rscript
# run_cytonorm.R — the ONLY R in the day-1 build. Reads a job dir, runs real
# CytoNorm (control-based batch normalization), writes corrected FCS back out.
# Python owns everything else (split, drift injection, EMD, UMAP, UI).
#
# Contract (minimal instance of PRD 2.5 file-based IPC):
#   <jobdir>/input/params.json     - config (below)
#   <jobdir>/input/control_*.fcs   - one control aliquot per batch (CytoNorm training)
#   <jobdir>/input/sample_*.fcs    - the batch samples to normalize
#   <jobdir>/output/Norm_*.fcs     - corrected samples  (written here)
#   <jobdir>/output/done.json      - completion signal Python polls for
#   <jobdir>/error.json            - written on failure
#
# Data arrives ALREADY arcsinh-transformed from Python -> transformList = NULL.
#
# NOTE: CytoNorm's exact arg names have shifted across versions. Verify this
# against the pinned image (`Rscript -e '?CytoNorm.train'`) during task T3 before
# relying on it. TODO markers flag the spots most likely to need a tweak.

suppressMessages({ library(flowCore); library(FlowSOM); library(CytoNorm); library(jsonlite) })

args   <- commandArgs(trailingOnly = TRUE)
jobdir <- if (length(args) >= 1) args[[1]] else "/job"
indir  <- file.path(jobdir, "input")
outdir <- file.path(jobdir, "output")
dir.create(outdir, showWarnings = FALSE, recursive = TRUE)

fail <- function(msg, tb = "") {
  write_json(list(status = "failed", error_message = msg, r_traceback = tb),
             file.path(jobdir, "error.json"), auto_unbox = TRUE)
  quit(save = "no", status = 1)
}

tryCatch({
  p <- fromJSON(file.path(indir, "params.json"))
  # params.json shape (written by backend/analysis/cytonorm.py):
  #   channels        : character vector of channel names to normalize
  #   control_files   : file names (in input/) of per-batch control aliquots
  #   control_labels  : batch label per control file (same order)
  #   sample_files    : file names of batch samples to normalize
  #   sample_labels   : batch label per sample file (same order)
  #   nClus           : metaclusters (default 10; keep < 30 per CytoNorm paper)
  #   nQ              : quantiles (default 101)
  #   seed            : RNG seed (default 42)
  channels <- p$channels
  nClus <- if (!is.null(p$nClus)) p$nClus else 10
  nQ    <- if (!is.null(p$nQ))    p$nQ    else 101
  seed  <- if (!is.null(p$seed))  p$seed  else 42

  ctrl_files <- file.path(indir, p$control_files)
  smpl_files <- file.path(indir, p$sample_files)

  # --- Train on the per-batch control aliquots -----------------------------
  # TODO(T3): confirm FlowSOM.params / normParams arg names against pinned CytoNorm.
  model <- CytoNorm.train(
    files          = ctrl_files,
    labels         = p$control_labels,
    channels       = channels,
    transformList  = NULL,                       # already transformed in Python
    FlowSOM.params = list(nCells = 1e6, xdim = 10, ydim = 10,
                          nClus = nClus, scale = FALSE),
    normMethod.train = QuantileNorm.train,
    normParams     = list(nQ = nQ, goal = "mean"),
    seed           = seed,
    verbose        = TRUE
  )

  # --- Apply to the batch samples ------------------------------------------
  CytoNorm.normalize(
    model                 = model,
    files                 = smpl_files,
    labels                = p$sample_labels,
    transformList         = NULL,
    transformList.reverse = NULL,
    outputDir             = outdir,
    prefix                = "Norm_",
    clean                 = TRUE,
    verbose               = TRUE
  )

  write_json(list(status = "completed",
                  n_controls = length(ctrl_files),
                  n_samples  = length(smpl_files),
                  nClus = nClus, nQ = nQ),
             file.path(outdir, "done.json"), auto_unbox = TRUE)
  cat("CytoNorm done\n")

}, error = function(e) {
  fail(conditionMessage(e), paste(deparse(sys.calls()), collapse = "\n"))
})
