#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Driver for the Loveless conversion (Phase 1). Two modes, picked by SUBSET_COL:
#
#   PASS 1  (SUBSET_COL unset) — FULL conversion. Heavy: download the 33 GB .rds,
#           run R extraction, assemble the full atlas h5ad, upload it + the schema
#           reports. Needs a >=256 GB CPU flavor (cpu-performance), ~hours.
#
#   PASS 2  (SUBSET_COL + SUBSET_VALUE set) — CHEAP subset-only. Skips Zenodo and
#           R entirely: pulls the full atlas h5ad that Pass 1 uploaded, carves out
#           the cohort subset (backed read), uploads it. Minutes; a small flavor
#           (cpu-xl) is plenty.
#
# Required env:
#   HF_TOKEN     write access to anne-voigt/pdac-research-data (set as a Job secret)
# Optional env:
#   WORK         scratch dir (default /data)
#   SUBSET_COL / SUBSET_VALUE   set BOTH to run Pass 2 (after Pass 1 reveals them)
# ---------------------------------------------------------------------------
set -euo pipefail

# Prefer the baked image's venv (Python deps live there, isolated from the base
# image's apt-managed packages). No-op on a stock image where it doesn't exist.
[ -d /opt/venv/bin ] && export PATH="/opt/venv/bin:$PATH"

WORK="${WORK:-/data}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO="anne-voigt/pdac-research-data"
ZENODO_URL="https://zenodo.org/records/14199536/files/scAtlas.rds.gz?download=1"
FULL_H5AD_REMOTE="loveless/loveless_atlas_counts.h5ad"

mkdir -p "$WORK"
cd "$WORK"

echo ">> python deps (anndata/scipy/pandas/huggingface_hub)"
# No-op when running the baked Dockerfile image (deps already present); only
# installs when invoked on a stock image. --break-system-packages covers PEP 668
# (Debian/rocker), with a fallback for older pip that doesn't know the flag.
if ! python3 -c 'import anndata, scipy, pandas, huggingface_hub' 2>/dev/null; then
  pip3 install --quiet --no-input --break-system-packages \
        anndata scipy pandas "huggingface_hub[cli]" \
    || pip3 install --quiet --no-input anndata scipy pandas "huggingface_hub[cli]"
fi

# ---- PASS 2: cheap subset-only (no Zenodo download, no R) ------------------
# SUBSET_VALUE may be a comma-separated list to emit several per-study subsets
# from ONE atlas download (e.g. "GSE155698,GSE205013"). Each value V is written
# and uploaded as loveless/V.h5ad.
if [ -n "${SUBSET_COL:-}" ]; then
  : "${SUBSET_VALUE:?set SUBSET_VALUE alongside SUBSET_COL for Pass 2}"
  echo ">> [subset] PASS 2 — fetching the full atlas h5ad from $REPO (no re-conversion)"
  hf download "$REPO" "$FULL_H5AD_REMOTE" --repo-type dataset --local-dir "$WORK/dl"
  ATLAS="$WORK/dl/$FULL_H5AD_REMOTE"
  IFS=',' read -ra VALS <<< "$SUBSET_VALUE"
  for raw in "${VALS[@]}"; do
    v="$(printf '%s' "$raw" | xargs)"                   # trim surrounding spaces
    safe="$(printf '%s' "$v" | tr -c 'A-Za-z0-9._-' '_')"  # filesystem-safe name
    # (printf, not echo: echo's trailing newline would become a stray '_')
    out="$WORK/${safe}.h5ad"
    echo ">> [subset] $SUBSET_COL == '$v'  ->  loveless/${safe}.h5ad"
    python3 "$HERE/subset_h5ad.py" \
      --in-h5ad "$ATLAS" --out "$out" \
      --subset-col "$SUBSET_COL" --subset-value "$v"
    hf upload "$REPO" "$out" "loveless/${safe}.h5ad" --repo-type dataset
  done
  echo ">> PASS 2 done — registered subsets: $SUBSET_VALUE"
  exit 0
fi

# ---- PASS 1: full conversion ----------------------------------------------
echo ">> [1/3] PASS 1 — download atlas from Zenodo (33.4 GB; resumable)"
if [ ! -f scAtlas.rds.gz ] && [ ! -f scAtlas.rds ]; then
  curl -L --fail --retry 5 -C - -o scAtlas.rds.gz "$ZENODO_URL"
fi

# Zenodo's scAtlas.rds.gz is DOUBLE-gzipped (gzip wrapping the already-gzip-
# compressed RDS that saveRDS writes). readRDS peels only ONE gzip layer, so on
# the raw .gz it hits the inner gzip and dies with "unknown input format". Peel
# the OUTER layer here; readRDS then handles the remaining inner gzip itself.
if [ ! -f scAtlas.rds ]; then
  echo ">> peeling outer gzip layer (file is double-gzipped)"
  gunzip -c scAtlas.rds.gz > scAtlas.rds
fi

echo ">> [2/3] R extraction -> intermediates"
# HF_REPO lets the R script upload schema_report.txt as soon as it's written, so
# the obs columns that unblock the manifest survive even if a later step fails.
export HF_REPO="$REPO"
Rscript "$HERE/convert_rds_to_h5ad.R" "$WORK/scAtlas.rds" "$WORK/intermediate"

echo ">> [3/3] Python assembly -> full atlas h5ad"
python3 "$HERE/assemble_h5ad.py" \
  --intermediates "$WORK/intermediate" \
  --out "$WORK/loveless_atlas_counts.h5ad"

echo ">> upload artifacts to private dataset repo $REPO (keeps old versions)"
hf upload "$REPO" "$WORK/intermediate/schema_report.txt"          loveless/schema_report.txt              --repo-type dataset
hf upload "$REPO" "$WORK/loveless_atlas_counts.obs_summary.txt"    loveless/loveless_atlas.obs_summary.txt --repo-type dataset
hf upload "$REPO" "$WORK/loveless_atlas_counts.h5ad"              "$FULL_H5AD_REMOTE"                      --repo-type dataset

echo ">> PASS 1 done. Read loveless/schema_report.txt + obs_summary on $REPO to find"
echo "   the cohort column + patient/sample key, then run Pass 2 with SUBSET_COL/VALUE."
