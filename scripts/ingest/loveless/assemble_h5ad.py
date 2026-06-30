#!/usr/bin/env python3
"""Assemble a counts-only .h5ad from the R-extracted intermediates (Pass 1).

Phase 1 (step 2) of the Loveless single-cell ingestion. Reads the MatrixMarket
counts + obs/var that ``convert_rds_to_h5ad.R`` produced and writes a gzip-
compressed AnnData. Peak RAM stays low because the counts never densify: they
load sparse and stay CSR (cells x genes).

Output is the FULL atlas (raw counts only) plus an ``*.obs_summary.txt`` listing
every obs column with cardinality + value counts. Read that summary (and the R
``schema_report.txt``) to learn the real cohort/study column and patient/sample
key, then run ``subset_h5ad.py`` (Pass 2) to carve out the analyzable subset —
no need to re-run this heavy conversion.

Usage:
  python3 assemble_h5ad.py --intermediates <dir> --out <atlas.h5ad>
"""
from __future__ import annotations

import argparse
import pathlib

import anndata as ad
import pandas as pd
import scipy.io


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--intermediates", required=True,
                    help="dir holding counts.mtx, genes.txt, barcodes.txt, obs.csv")
    ap.add_argument("--out", required=True, help="output .h5ad path (full atlas)")
    args = ap.parse_args()

    d = pathlib.Path(args.intermediates)
    genes = (d / "genes.txt").read_text().splitlines()
    barcodes = (d / "barcodes.txt").read_text().splitlines()
    obs = pd.read_csv(d / "obs.csv", index_col=0)
    obs.index = obs.index.astype(str)

    # MatrixMarket is genes x cells (R orientation) -> transpose to cells x genes.
    X = scipy.io.mmread(d / "counts.mtx").tocsr().T.tocsr()
    if X.shape != (len(barcodes), len(genes)):
        raise SystemExit(
            f"shape mismatch: counts {X.shape} vs "
            f"{len(barcodes)} barcodes x {len(genes)} genes"
        )

    var = pd.DataFrame(index=pd.Index(genes, name="gene_symbol"))
    obs = obs.reindex(barcodes)  # align obs rows to the count-matrix column order

    adata = ad.AnnData(X=X, obs=obs, var=var)
    adata.layers["counts"] = adata.X.copy()  # keep an explicit raw-counts layer

    _write_obs_summary(adata, pathlib.Path(args.out).with_suffix(".obs_summary.txt"))

    adata.write_h5ad(args.out, compression="gzip")
    print(f"wrote {args.out}  shape={adata.shape}")


def _write_obs_summary(adata: "ad.AnnData", path: pathlib.Path) -> None:
    """Dump every obs column's cardinality + (low-cardinality) value counts."""
    with open(path, "w") as fh:
        fh.write(f"shape (cells x genes): {adata.shape}\n\n")
        for c in adata.obs.columns:
            col = adata.obs[c]
            n_unique = col.nunique(dropna=False)
            fh.write(f"== {c} ==  dtype={col.dtype}  n_unique={n_unique}\n")
            if n_unique <= 60:
                fh.write(col.value_counts(dropna=False).to_string() + "\n")
            fh.write("\n")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
