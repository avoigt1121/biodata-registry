#!/usr/bin/env python3
"""Assemble a counts-only .h5ad from the R-extracted intermediates.

Phase 1 (step 2) of the Loveless single-cell ingestion. Reads the MatrixMarket
counts + obs/var that ``convert_rds_to_h5ad.R`` produced and writes a gzip-
compressed AnnData. Peak RAM stays low because the counts never densify: they
load sparse and stay CSR (cells x genes).

Two passes are expected:
  * Pass 1 (no --subset-col): build the full-atlas counts h5ad AND an
    ``*.obs_summary.txt`` listing every obs column with cardinality + value
    counts. Read that summary (and the R schema_report.txt) to learn the real
    cohort/study column and patient/sample key.
  * Pass 2 (--subset-col/--subset-value): additionally write the Steele-cohort
    subset (``*_subset.h5ad``) — the analyzable dataset that gets registered.
    The full atlas stays an offline reference only (batch-corrected, ~100 GB+).

Usage:
  python3 assemble_h5ad.py --intermediates <dir> --out <atlas.h5ad> \
      [--subset-col <obs_col> --subset-value <value>]
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
    ap.add_argument("--subset-col", default=None,
                    help="obs column to subset on (e.g. the cohort/study column)")
    ap.add_argument("--subset-value", default=None,
                    help="value of --subset-col to keep (e.g. the Steele cohort label)")
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

    if args.subset_col:
        if args.subset_col not in adata.obs.columns:
            raise SystemExit(
                f"--subset-col '{args.subset_col}' not in obs; "
                f"columns: {list(adata.obs.columns)}"
            )
        if args.subset_value is None:
            raise SystemExit("--subset-col given without --subset-value")
        mask = adata.obs[args.subset_col].astype(str) == str(args.subset_value)
        sub = adata[mask].copy()
        out = pathlib.Path(args.out)
        sub_path = out.with_name(out.stem + "_subset.h5ad")
        sub.write_h5ad(sub_path, compression="gzip")
        print(f"wrote {sub_path}  shape={sub.shape} "
              f"({args.subset_col}=={args.subset_value})")


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
