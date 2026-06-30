#!/usr/bin/env python3
"""Subset an already-built atlas h5ad to one cohort — the cheap Pass 2.

Avoids re-downloading the 33 GB .rds and re-running the R conversion: it reads
the full counts h5ad that Pass 1 produced (and uploaded) and writes the cohort
subset — the analyzable dataset that gets registered. Minutes, not hours.

Loads the atlas in backed mode so the full dense object never sits in RAM; only
the selected cells are materialised before writing.

Usage:
  python3 subset_h5ad.py --in-h5ad <atlas.h5ad> --out <subset.h5ad> \
      --subset-col <obs_col> --subset-value <value>
"""
from __future__ import annotations

import argparse

import anndata as ad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--in-h5ad", required=True, help="path to the full atlas h5ad")
    ap.add_argument("--out", required=True, help="output subset .h5ad path")
    ap.add_argument("--subset-col", required=True,
                    help="obs column to filter on (e.g. the cohort/study column)")
    ap.add_argument("--subset-value", required=True,
                    help="value of --subset-col to keep (e.g. the Steele cohort label)")
    args = ap.parse_args()

    # backed='r' keeps the full matrix on disk; we densify only the kept cells.
    adata = ad.read_h5ad(args.in_h5ad, backed="r")
    if args.subset_col not in adata.obs.columns:
        raise SystemExit(
            f"--subset-col '{args.subset_col}' not in obs; "
            f"columns: {list(adata.obs.columns)}"
        )
    mask = adata.obs[args.subset_col].astype(str) == str(args.subset_value)
    n = int(mask.sum())
    if n == 0:
        vals = adata.obs[args.subset_col].astype(str).unique()[:20]
        raise SystemExit(
            f"no cells match {args.subset_col}=={args.subset_value!r}; "
            f"sample values: {list(vals)}"
        )

    sub = adata[mask].to_memory()
    sub.write_h5ad(args.out, compression="gzip")
    print(f"wrote {args.out}  shape={sub.shape}  "
          f"({args.subset_col}=={args.subset_value}, {n} cells)")


if __name__ == "__main__":
    main()
