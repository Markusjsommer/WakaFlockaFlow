#!/usr/bin/env Rscript
# run_unmix.R — spectral unmixing via AutoSpectral (DrCytometer/AutoSpectral, AGPL-3.0).
# Raw detector FCS + single-stain controls -> per-marker unmixed FCS.
#
# Validated on the flowSpecs Aurora PBMC set: the unmixed output passes the biology
# check (CD3/CD19 anti-correlated; CD3/CD8, CD3/CD4 positively correlated).
#
# Contract (file-based IPC, mirrors run_cytonorm.R):
#   <jobdir>/input/raw.fcs           - raw detector sample to unmix
#   <jobdir>/input/controls/*.fcs    - single-stain + unstained controls
#   <jobdir>/input/params.json       - {cytometer, af_control, ...} (optional)
#   <jobdir>/output/*.fcs            - unmixed sample (written here)
#   <jobdir>/output/done.json | <jobdir>/error.json
#
# Control-file completion notes (the fiddly, AutoSpectral-specific bits, solved):
#   - universal.negative must be the FILENAME of the paired negative (e.g.
#     "Beads_unstained.fcs"), NOT a boolean.
#   - the primary-cell unstained control is designated fluorophore == "AF".
#   - get.af.spectra needs explicit plot.dir/table.dir (asp$figure.af.dir is unset
#     when figures=FALSE, else dir.create(NULL) throws "invalid filename argument").
#   - method="AutoSpectral" requires the multi-row AF matrix from get.af.spectra.

suppressMessages(library(AutoSpectral))

args   <- commandArgs(trailingOnly = TRUE)
jobdir <- if (length(args) >= 1) args[[1]] else "/job"
indir  <- file.path(jobdir, "input")
outdir <- file.path(jobdir, "output")
ctrldir <- file.path(indir, "controls")
dir.create(outdir, showWarnings = FALSE, recursive = TRUE)
afplt <- file.path(jobdir, "af_plots"); dir.create(afplt, showWarnings = FALSE)
aftbl <- file.path(jobdir, "af_tables"); dir.create(aftbl, showWarnings = FALSE)

fail <- function(msg) {
  jsonlite::write_json(list(status = "failed", error_message = msg),
                       file.path(jobdir, "error.json"), auto_unbox = TRUE)
  quit(save = "no", status = 1)
}

tryCatch({
  params <- if (file.exists(file.path(indir, "params.json")))
    jsonlite::fromJSON(file.path(indir, "params.json")) else list()
  cytometer <- if (!is.null(params$cytometer)) params$cytometer else "aurora"
  af.control <- if (!is.null(params$af_control)) params$af_control else "PBMC_unstained.fcs"
  bead.negative <- if (!is.null(params$bead_negative)) params$bead_negative else "Beads_unstained.fcs"

  asp <- get.autospectral.param(cytometer = cytometer, figures = FALSE)
  setwd(ctrldir)
  cf <- "fcs_control_file.csv"
  suppressWarnings(create.control.file(ctrldir, asp, filename = "fcs_control_file", legacy = FALSE))

  df <- read.csv(file.path(ctrldir, cf), stringsAsFactors = FALSE)
  # --- complete the control file (see notes above) ---
  # read.csv turns empty cells into NA; coerce character NAs to "" so downstream
  # logicals never yield NA (AutoSpectral's validate.control.file does if(any(...))
  # over control.type and errors on "missing value where TRUE/FALSE needed").
  chr <- vapply(df, is.character, logical(1))
  df[chr] <- lapply(df[chr], function(x) { x[is.na(x)] <- ""; x })

  is.bead <- grepl("bead", df$filename, ignore.case = TRUE)
  # control.type deterministically from filename -> never NA
  df$control.type <- ifelse(is.bead, "beads", "cells")
  # designate the primary-cell autofluorescence control; blank the other negatives
  df$fluorophore[df$filename == af.control] <- "AF"
  df$fluorophore[grepl("unstained", df$filename, ignore.case = TRUE) & df$filename != af.control] <- ""
  # per-fluorophore paired negative: bead controls -> bead negative; cell controls -> AF
  df$universal.negative <- ""
  has.fluor <- !(df$fluorophore %in% c("", "AF", "No match"))
  df$universal.negative[has.fluor & is.bead] <- bead.negative
  df$universal.negative[has.fluor & !is.bead] <- af.control
  # viability dye (cell-based dead-cell control)
  via <- grepl("dead|dcm|viab|live", df$filename, ignore.case = TRUE) & has.fluor
  df$is.viability[via] <- TRUE
  df$marker[df$filename == "Beads_FITC_CD41b.fcs"] <- "CD41b"
  write.csv(df, file.path(ctrldir, cf), row.names = FALSE)

  check.control.file(ctrldir, cf, asp)

  spectra <- get.spectra.automated(ctrldir, cf, asp, figures = FALSE, verbose = FALSE)
  # drop blank endmember rows (unmatched negatives)
  keep <- !(rownames(spectra) %in% "" | grepl("^\\.", rownames(spectra)))
  spectra <- spectra[keep, , drop = FALSE]

  af <- get.af.spectra(unstained.sample = file.path(ctrldir, af.control),
                       asp = asp, spectra = spectra,
                       figures = FALSE, save = FALSE, verbose = FALSE, parallel = FALSE,
                       plot.dir = afplt, table.dir = aftbl)

  unmix.fcs(file.path(indir, "raw.fcs"), spectra, asp, NULL,
            method = "AutoSpectral", af.spectra = af,
            output.dir = outdir, verbose = FALSE)

  jsonlite::write_json(list(status = "completed",
                            n_fluorophores = nrow(spectra),
                            output_files = list.files(outdir, pattern = "\\.fcs$")),
                       file.path(outdir, "done.json"), auto_unbox = TRUE)
  cat("Unmixing done\n")
}, error = function(e) fail(conditionMessage(e)))
