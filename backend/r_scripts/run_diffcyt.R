#!/usr/bin/env Rscript
# Differential abundance (edgeR) + differential state (limma) for a cohort run.
#
# Implements the diffcyt method (Weber et al. 2019) directly on precomputed
# per-sample cluster counts and per-cluster marker medians, so no reclustering is
# needed. Same file-IPC contract as run_unmix.R / run_cytonorm.R:
#   <jobdir>/input/{counts.csv, sample_info.csv, medians.csv, params.json}
#   <jobdir>/output/{da.csv, ds.csv, done.json}  (or <jobdir>/error.json)

args <- commandArgs(trailingOnly = TRUE)
jobdir <- args[1]
indir <- file.path(jobdir, "input")
outdir <- file.path(jobdir, "output")
dir.create(outdir, showWarnings = FALSE, recursive = TRUE)

fail <- function(msg) {
  jsonlite::write_json(list(error_message = as.character(msg)),
                       file.path(jobdir, "error.json"), auto_unbox = TRUE)
  quit(save = "no", status = 0)
}

tryCatch({
  suppressMessages({
    library(edgeR)
    library(limma)
    library(jsonlite)
  })

  params <- fromJSON(file.path(indir, "params.json"))
  counts <- read.csv(file.path(indir, "counts.csv"), check.names = FALSE)
  info <- read.csv(file.path(indir, "sample_info.csv"), check.names = FALSE)
  med <- read.csv(file.path(indir, "medians.csv"), check.names = FALSE)

  samp_cols <- as.character(info$sample_index)
  mc <- as.character(counts$metacluster_id)
  cmat <- as.matrix(counts[, samp_cols, drop = FALSE])
  rownames(cmat) <- mc

  field <- params$group_field
  grp <- if (identical(field, "batch")) info$batch else info$group
  grp <- as.character(grp)

  contrast <- params$contrast
  if (!is.null(contrast) && length(contrast) >= 2) {
    keep <- grp %in% contrast
    cmat <- cmat[, keep, drop = FALSE]
    grp <- grp[keep]
    samp_cols <- samp_cols[keep]
    grp <- factor(grp, levels = contrast)
  } else {
    grp <- factor(grp)
  }
  if (nlevels(grp) < 2) fail("differential testing needs at least two groups")

  design <- model.matrix(~ grp)

  # ---- differential abundance: edgeR quasi-likelihood on cluster counts ----
  dge <- DGEList(counts = cmat)
  dge <- calcNormFactors(dge)
  dge <- estimateDisp(dge, design)
  fit <- glmQLFit(dge, design)
  qlf <- glmQLFTest(fit, coef = 2)  # second level vs the reference
  tt <- topTags(qlf, n = Inf, sort.by = "none")$table
  da <- data.frame(
    metacluster_id = rownames(cmat),
    log_fc = tt$logFC, p_value = tt$PValue, p_adj = tt$FDR, log_cpm = tt$logCPM,
    stringsAsFactors = FALSE
  )
  write.csv(da, file.path(outdir, "da.csv"), row.names = FALSE)

  # ---- differential state: limma on per-(cluster,marker) median expression ----
  markers <- unique(med$marker)
  blocks <- list()
  for (mk in markers) {
    sub <- med[med$marker == mk, c("metacluster_id", "sample_index", "value")]
    w <- reshape(sub, idvar = "metacluster_id", timevar = "sample_index",
                 direction = "wide")
    rn <- as.character(w$metacluster_id)
    w$metacluster_id <- NULL
    colnames(w) <- sub("value\\.", "", colnames(w))
    m <- as.matrix(w[, samp_cols, drop = FALSE])
    rownames(m) <- paste0(rn, "||", mk)
    blocks[[mk]] <- m
  }
  ds_mat <- do.call(rbind, blocks)
  fitv <- eBayes(lmFit(ds_mat, design))
  tv <- topTable(fitv, coef = 2, number = Inf, sort.by = "none")
  parts <- strsplit(rownames(tv), "\\|\\|")
  ds <- data.frame(
    metacluster_id = sapply(parts, `[`, 1),
    marker = sapply(parts, `[`, 2),
    log_fc = tv$logFC, p_value = tv$P.Value, p_adj = tv$adj.P.Val,
    stringsAsFactors = FALSE
  )
  write.csv(ds, file.path(outdir, "ds.csv"), row.names = FALSE)

  jsonlite::write_json(list(engine = "diffcyt", n_da = nrow(da), n_ds = nrow(ds)),
                       file.path(outdir, "done.json"), auto_unbox = TRUE)
}, error = function(e) fail(conditionMessage(e)))
