#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# In-container driver for the Loveless .rds -> h5ad conversion (Phase 1).
# Runs ALL steps inside one HF Job: download -> R extract -> Python assemble ->
# upload to the private HF dataset repo. Designed for a >=256 GB CPU flavor.
#
# Required env:
#   HF_TOKEN     write access to anne-voigt/pdac-research-data (set as a Job secret)
# Optional env:
#   WORK         scratch dir (default /data)
#   SUBSET_COL   obs column to subset the analyzable dataset on  (PASS 2 only)
#   SUBSET_VALUE value of SUBSET_COL to keep                     (PASS 2 only)
#
# PASS 1 (discover schema): run with no SUBSET_*; read the uploaded
#         loveless/schema_report.txt + *.obs_summary.txt to find the cohort
#         column + patient/sample key. PASS 2: re-run with SUBSET_COL/VALUE set
#         to also emit the Steele-cohort analyzable subset.
# ---------------------------------------------------------------------------
set -euo pipefail

WORK="${WORK:-/data}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="anne-voigt/pdac-research-data"
ZENODO_URL="https://zenodo.org/records/14199536/files/scAtlas.rds.gz?download=1"

mkdir -p "$WORK"
cd "$WORK"

echo ">> [1/4] python deps (anndata/scipy/pandas/huggingface_hub)"
# No-op when running the baked Dockerfile image (deps already present); only
# installs when invoked on a stock image. --break-system-packages covers PEP 668
# (Debian/rocker), with a fallback for older pip that doesn't know the flag.
if ! python3 -c 'import anndata, scipy, pandas, huggingface_hub' 2>/dev/null; then
  pip3 install --quiet --no-input --break-system-packages \
        anndata scipy pandas "huggingface_hub[cli]" \
    || pip3 install --quiet --no-input anndata scipy pandas "huggingface_hub[cli]"
fi

echo ">> [2/4] download atlas from Zenodo (33.4 GB; resumable)"
if [ ! -f scAtlas.rds.gz ]; then
  curl -L --fail --retry 5 -C - -o scAtlas.rds.gz "$ZENODO_URL"
fi

echo ">> [3/4] R extraction -> intermediates"
Rscript "$HERE/convert_rds_to_h5ad.R" "$WORK/scAtlas.rds.gz" "$WORK/intermediate"

echo ">> [4/4] Python assembly -> h5ad"
python3 "$HERE/assemble_h5ad.py" \
  --intermediates "$WORK/intermediate" \
  --out "$WORK/loveless_atlas_counts.h5ad" \
  ${SUBSET_COL:+--subset-col "$SUBSET_COL"} \
  ${SUBSET_VALUE:+--subset-value "$SUBSET_VALUE"}

echo ">> upload artifacts to private dataset repo $REPO (keeps old versions)"
hf upload "$REPO" "$WORK/intermediate/schema_report.txt"          loveless/schema_report.txt          --repo-type dataset
hf upload "$REPO" "$WORK/loveless_atlas_counts.obs_summary.txt"    loveless/loveless_atlas.obs_summary.txt --repo-type dataset
hf upload "$REPO" "$WORK/loveless_atlas_counts.h5ad"              loveless/loveless_atlas_counts.h5ad --repo-type dataset
if [ -f "$WORK/loveless_atlas_counts_subset.h5ad" ]; then
  hf upload "$REPO" "$WORK/loveless_atlas_counts_subset.h5ad"     loveless/loveless_steele_subset.h5ad --repo-type dataset
fi

echo ">> done. Inspect loveless/schema_report.txt + obs_summary on $REPO, then fill the manifest."
