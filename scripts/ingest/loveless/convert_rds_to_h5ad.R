#!/usr/bin/env Rscript
# ---------------------------------------------------------------------------
# Loveless atlas  scAtlas.rds(.gz)  ->  intermediate files for h5ad assembly
# ---------------------------------------------------------------------------
# Phase 1 of the Loveless single-cell ingestion (see biodata-registry TODO and
# DecoupleRpy_Agent ADR-0006). MEMORY-BOUND: the integrated atlas is >700k cells
# and ~33 GB compressed; readRDS holds the whole Seurat object in RAM, so run
# this on a >=256 GB CPU HF Job, never a laptop.
#
# This step does TWO things:
#   1. Writes schema_report.txt FIRST (cheap) — the real assay/obs column names
#      and value counts. This is what unblocks the manifest: we fill it from the
#      *actual* obs/var, never by guessing columns. In particular it surfaces the
#      cohort/study column and the patient/sample key (the pseudobulk aggregation
#      key — the critical field).
#   2. Extracts ONLY the raw counts layer (+ obs + gene/cell names) to
#      MatrixMarket + CSV. Corrected / scaled / integrated layers are dropped —
#      the single biggest lever on peak RAM and output size, and they are
#      confounded for DE anyway (the atlas is batch-corrected across studies).
#
# Usage:  Rscript convert_rds_to_h5ad.R <in_rds(.gz)> <out_dir>
# Output: <out_dir>/{schema_report.txt, counts.mtx, genes.txt, barcodes.txt, obs.csv}
# ---------------------------------------------------------------------------

suppressMessages({
  library(Matrix)
  library(Seurat)
  library(SeuratObject)
})

args <- commandArgs(trailingOnly = TRUE)
if (length(args) < 2) {
  stop("usage: Rscript convert_rds_to_h5ad.R <in_rds(.gz)> <out_dir>")
}
in_rds  <- args[[1]]
out_dir <- args[[2]]
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)

# The driver peels the OUTER gzip; this file is the inner gzip-compressed RDS,
# which readRDS decompresses transparently (gzfile detects by content, not name).
message(">> reading ", in_rds, " (memory-heavy step)")
obj <- readRDS(in_rds)
message(">> loaded object of class: ", paste(class(obj), collapse = ", "))

# ---- 1. schema report (do this before trusting any column name) -----------
assay_names <- tryCatch(SeuratObject::Assays(obj),
                        error = function(e) names(obj@assays))
def_assay <- tryCatch(DefaultAssay(obj),
                      error = function(e) assay_names[[1]])
md <- as.data.frame(obj@meta.data)

report_path <- file.path(out_dir, "schema_report.txt")
writeLines(capture.output({
  cat("default_assay:", def_assay, "\n")
  cat("assays:", paste(assay_names, collapse = ", "), "\n")
  cat("n_cells:", ncol(obj), "  n_genes(", def_assay, "):", nrow(obj), "\n")
  cat("\n== meta.data column classes ==\n")
  print(vapply(md, function(x) class(x)[[1]], character(1)))
  cat("\n== low-cardinality columns (<=60 uniques): value counts ==\n")
  cat("   (look here for the cohort/study column and the patient/sample key)\n")
  for (cn in colnames(md)) {
    vals <- md[[cn]]
    u <- unique(vals)
    if (length(u) <= 60) {
      cat("\n-- ", cn, " --\n", sep = "")
      print(sort(table(vals, useNA = "ifany"), decreasing = TRUE))
    } else {
      cat("\n-- ", cn, " -- (", length(u),
          " uniques; high cardinality, e.g. cell/sample IDs)\n", sep = "")
    }
  }
}), report_path)
message(">> wrote ", report_path,
        " — INSPECT THIS to identify the cohort/study + patient/sample columns")

# Upload the schema report immediately (if HF_REPO is set), so the obs columns
# that unblock the manifest are saved even if counts extraction later fails.
repo <- Sys.getenv("HF_REPO", "")
if (nzchar(repo)) {
  message(">> uploading schema_report.txt early to ", repo)
  try(system2("hf", c("upload", repo, report_path,
                      "loveless/schema_report.txt", "--repo-type", "dataset")),
      silent = TRUE)
}

# ---- 2. extract raw counts only, drop everything else ---------------------
# Prefer the RNA assay's raw counts; an integrated/SCT default assay may hold
# corrected values, not raw counts.
assay_for_counts <- if ("RNA" %in% assay_names) "RNA" else def_assay
message(">> extracting counts from assay: ", assay_for_counts)

# Seurat v5 can split counts across per-batch layers (counts.1, counts.2, …)
# after a merge; JoinLayers consolidates them into one 'counts' layer. No-op for
# v4 objects (wrapped so a missing/failed join doesn't abort).
obj <- tryCatch(
  SeuratObject::JoinLayers(obj, assay = assay_for_counts),
  error = function(e) { message(">> JoinLayers skipped: ", conditionMessage(e)); obj }
)

# Seurat v5 exposes layers; v4 used slots. Try the v5 path first.
counts <- tryCatch(
  SeuratObject::LayerData(obj, assay = assay_for_counts, layer = "counts"),
  error = function(e) GetAssayData(obj, assay = assay_for_counts, slot = "counts")
)
if (is.null(counts) || nrow(counts) == 0) {
  stop("could not extract a non-empty 'counts' layer/slot from assay '",
       assay_for_counts, "' — check schema_report.txt for the raw-counts assay name")
}

genes    <- rownames(counts)
barcodes <- colnames(counts)
rm(obj); gc()
message(">> counts: ", nrow(counts), " genes x ", ncol(counts),
        " cells; writing MatrixMarket + CSV")

writeMM(counts, file.path(out_dir, "counts.mtx"))
writeLines(genes,    file.path(out_dir, "genes.txt"))
writeLines(barcodes, file.path(out_dir, "barcodes.txt"))
write.csv(md, file.path(out_dir, "obs.csv"), row.names = TRUE)

message(">> done. Intermediates in ", out_dir)
