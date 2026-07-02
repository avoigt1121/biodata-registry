#!/usr/bin/env python
"""Derive Role-2 cell-type signatures from a Loveless single-cell subset.

ADR-0006 (DecoupleRpy_Agent) Role 2: the full Loveless atlas is never served
live. Instead, per-cell-type marker signatures are derived OFFLINE from a subset
and published as a plain ``source, target, weight`` table, which the agent scores
against bulk cohorts via ``dataset_score_signature`` (decoupleR ULM). This script
is that offline derivation step.

The signature is DERIVED FROM THE DATA (scanpy ``rank_genes_groups`` on the
``Clusters`` cell-type labels), never hand-written — so the published artifact is
reproducible and grounded, consistent with the project's anti-hallucination stance.

Output schema (one row per gene-in-signature), exactly what
``src/workflows/signatures.py::load_signature_net`` consumes:

    source,target,weight
    <cell_type>,<HGNC gene symbol>,<log2 fold-change>

Usage
-----
    # dry run — derive + write CSV locally, do NOT upload
    python derive_signatures.py --dataset steele

    # derive + publish to the pdac-research-data HF dataset
    python derive_signatures.py --dataset steele --publish

Auth: reads the cached HF token (`huggingface-cli login`) or $HF_TOKEN. Read is
needed for the (private) subset download; write is needed only for --publish.
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np
import pandas as pd

# Subset h5ads as hosted on the pdac-research-data dataset repo (see the
# gse155698_steele / gse205013_werba manifests). Keyed by the short --dataset id.
HF_DATASET_REPO = "anne-voigt/pdac-research-data"
SUBSETS = {
    "steele": "loveless/GSE155698.h5ad",   # Steele 2020, GSE155698 (smaller cohort)
    "werba":  "loveless/GSE205013.h5ad",   # Werba 2023, GSE205013 (~167k cells — heavier)
}
CELLTYPE_OBS_CANDIDATES = ("Clusters", "celltype", "cell_type", "CellType")


def _get_token() -> str | None:
    try:
        from huggingface_hub import get_token
        tok = get_token()
    except Exception:
        tok = None
    return tok or os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")


def _find_celltype_col(adata) -> str:
    for c in CELLTYPE_OBS_CANDIDATES:
        if c in adata.obs.columns:
            return c
    raise SystemExit(
        f"No cell-type column found in obs (looked for {CELLTYPE_OBS_CANDIDATES}). "
        f"Available: {list(adata.obs.columns)}"
    )


def derive(adata, celltype_col: str, top_n: int, min_lfc: float, max_padj: float) -> pd.DataFrame:
    """Return a source/target/weight signature table via rank_genes_groups."""
    import scanpy as sc

    adata = adata.copy()
    # rank_genes_groups expects log-normalised values. The subset is raw counts.
    sc.pp.normalize_total(adata, target_sum=1e4)
    sc.pp.log1p(adata)

    # Drop tiny / unlabeled groups so a signature isn't built from noise.
    adata.obs[celltype_col] = adata.obs[celltype_col].astype("category")
    counts = adata.obs[celltype_col].value_counts()
    keep = counts[counts >= 20].index.tolist()
    bad = {"", "NA", "nan", "N_A", "Unknown"}
    keep = [g for g in keep if str(g) not in bad]
    adata = adata[adata.obs[celltype_col].isin(keep)].copy()
    adata.obs[celltype_col] = adata.obs[celltype_col].cat.remove_unused_categories()

    sc.tl.rank_genes_groups(adata, groupby=celltype_col, method="wilcoxon")
    res = adata.uns["rank_genes_groups"]
    groups = res["names"].dtype.names

    rows = []
    for g in groups:
        df = pd.DataFrame({
            "target": res["names"][g],
            "weight": res["logfoldchanges"][g],
            "padj": res["pvals_adj"][g],
        })
        df = df[(df["weight"] >= min_lfc) & (df["padj"] <= max_padj)]
        df = df.sort_values("weight", ascending=False).head(top_n)
        df["source"] = str(g)
        rows.append(df[["source", "target", "weight"]])

    net = pd.concat(rows, ignore_index=True)
    net["target"] = net["target"].astype(str)
    net = net[net["target"].str.strip().astype(bool)].reset_index(drop=True)
    return net


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", choices=sorted(SUBSETS), default="steele")
    ap.add_argument("--top-n", type=int, default=50, help="Top marker genes per cell type.")
    ap.add_argument("--min-lfc", type=float, default=1.0, help="Min log2 fold-change.")
    ap.add_argument("--max-padj", type=float, default=0.05, help="Max adjusted p-value.")
    ap.add_argument("--out", default=None, help="Local CSV path (default derived from --dataset).")
    ap.add_argument("--publish", action="store_true", help="Upload the CSV to pdac-research-data.")
    args = ap.parse_args()

    from huggingface_hub import hf_hub_download

    token = _get_token()
    if token is None:
        raise SystemExit(
            "No HF token found. Run `huggingface-cli login` (read on "
            f"{HF_DATASET_REPO} + write for --publish) or set $HF_TOKEN."
        )

    import scanpy as sc

    filename = SUBSETS[args.dataset]
    print(f"[1/4] downloading {HF_DATASET_REPO}:{filename} …", flush=True)
    local = hf_hub_download(repo_id=HF_DATASET_REPO, filename=filename,
                            repo_type="dataset", token=token)
    adata = sc.read_h5ad(local)
    ct = _find_celltype_col(adata)
    print(f"      loaded {adata.n_obs:,} cells x {adata.n_vars:,} genes; cell-type col '{ct}'", flush=True)

    print("[2/4] deriving signatures (rank_genes_groups, wilcoxon) …", flush=True)
    net = derive(adata, ct, args.top_n, args.min_lfc, args.max_padj)
    n_sig = net["source"].nunique()
    print(f"      {n_sig} cell-type signatures, {len(net)} gene rows", flush=True)
    print(net.groupby("source")["target"].size().to_string(), flush=True)

    out = args.out or f"gse{'155698_steele' if args.dataset=='steele' else '205013_werba'}_celltype_signatures.csv"
    net.to_csv(out, index=False)
    print(f"[3/4] wrote {out}", flush=True)

    if args.publish:
        from huggingface_hub import upload_file
        path_in_repo = f"loveless/signatures/{os.path.basename(out)}"
        print(f"[4/4] uploading -> {HF_DATASET_REPO}:{path_in_repo} …", flush=True)
        upload_file(path_or_fileobj=out, path_in_repo=path_in_repo,
                    repo_id=HF_DATASET_REPO, repo_type="dataset", token=token,
                    commit_message=f"Add Loveless {args.dataset} cell-type signatures (Role-2 artifact)")
        print(f"      published: https://huggingface.co/datasets/{HF_DATASET_REPO}/resolve/main/{path_in_repo}", flush=True)
    else:
        print("[4/4] --publish not set; local only (dry run).", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
