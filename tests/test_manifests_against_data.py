"""
Live-data tests: verify each manifest's declared semantics against the real h5ad.

Unlike test_registry.py (schema-only, offline), this module downloads each
dataset's precomputed h5ad from HuggingFace and asserts the manifest actually
matches the data:

  * every declared metadata column exists in obs
  * declared allowed_values cover the real obs values (the check that caught the
    paca_au_rnaseq "Cell line " trailing-space / "Metastatic tumour" bug)
  * feature_id_type is consistent with var.index
  * data_level range sanity (raw_counts are non-negative integers)
  * default_sample_filter / default_contrasts subset_query / survival columns all
    reference real obs columns and evaluate without error (the generalized guard
    against the obs['col'].isin(...) query-syntax bug)
  * curated_sample_list barcodes (TCGA) are present in the loaded samples

These tests need network access and HF bandwidth, so they are OPT-IN: the whole
module is skipped unless RUN_LIVE_DATA_TESTS=1. Downloaded h5ads are cached
between runs (override the location with BIODATA_TEST_CACHE).

    RUN_LIVE_DATA_TESTS=1 pytest tests/test_manifests_against_data.py -v
    RUN_LIVE_DATA_TESTS=1 pytest -m live -v
"""

from __future__ import annotations

import math
import os
import tempfile
import urllib.request
from pathlib import Path

import pytest

from biodata_registry import get_registry, load_manifest
from biodata_registry.manifest_schema import MetadataColumnDef

# --- Opt-in gate + heavy deps ------------------------------------------------

if os.environ.get("RUN_LIVE_DATA_TESTS") != "1":
    pytest.skip(
        "live-data tests are opt-in; set RUN_LIVE_DATA_TESTS=1 to run",
        allow_module_level=True,
    )

anndata = pytest.importorskip("anndata")
np = pytest.importorskip("numpy")
_sparse = pytest.importorskip("scipy.sparse")

pytestmark = pytest.mark.live

# Datasets whose data_level intentionally cannot be auto-classified from value
# range alone (documented in their manifests). We skip the range sanity check
# for these rather than assert against a non-standard scale.
_DATA_LEVEL_RANGE_EXEMPT = {"gse16515_mayo", "puleo_2018"}


# --- Download + cache --------------------------------------------------------

def _cache_dir() -> Path:
    d = os.environ.get("BIODATA_TEST_CACHE") or os.path.join(
        tempfile.gettempdir(), "biodata_registry_test_cache"
    )
    p = Path(d)
    p.mkdir(parents=True, exist_ok=True)
    return p


_ADATA_CACHE: dict[str, "anndata.AnnData"] = {}


def _load_adata(dataset_id: str) -> "anndata.AnnData":
    """Download (cached) and read the dataset's h5ad, memoized per session."""
    if dataset_id in _ADATA_CACHE:
        return _ADATA_CACHE[dataset_id]

    manifest = load_manifest(dataset_id)
    url = manifest.expression_source.get("url")
    if not url:
        pytest.skip(f"{dataset_id}: no expression_source.url to fetch")

    local = _cache_dir() / f"{dataset_id}.h5ad"
    if not local.exists():
        tmp = local.with_suffix(".h5ad.part")
        urllib.request.urlretrieve(url, tmp)  # noqa: S310 (trusted HF URLs)
        tmp.rename(local)

    adata = anndata.read_h5ad(local)
    _ADATA_CACHE[dataset_id] = adata
    return adata


# --- Helpers -----------------------------------------------------------------

def _canon(v) -> tuple[str, object]:
    """
    Canonicalize a value for allowed_values comparison.

    Numeric values compare numerically so that obs int 1, float 1.0, and the
    YAML strings "1" / "1.0" all match — these differ only in storage format.
    Non-numeric strings are kept verbatim (NOT whitespace-stripped) so genuine
    mismatches like the "Cell line " trailing-space bug are still detected.
    """
    s = v if isinstance(v, str) else str(v)
    try:
        f = float(s)
    except (ValueError, TypeError):
        return ("str", s)
    # NaN/inf never compare equal to themselves, which would break set membership;
    # keep them as string tokens (e.g. the literal "nan" used in missing_values).
    if math.isnan(f) or math.isinf(f):
        return ("str", s)
    return ("num", f)


def _obs_canon_values(series) -> set:
    """Unique non-null obs values in canonical form."""
    return {_canon(v) for v in series.dropna().unique()}


def _x_min_and_integral(adata) -> tuple[float, bool]:
    """Return (global min, whether all values are integral). Handles sparse."""
    X = adata.X
    if _sparse.issparse(X):
        data = X.data
        gmin = float(data.min()) if data.size else 0.0
        # implicit zeros are integral, so only the stored data matters
        integral = bool(np.all(np.mod(data, 1) == 0))
    else:
        arr = np.asarray(X)
        gmin = float(np.nanmin(arr)) if arr.size else 0.0
        integral = bool(np.all(np.mod(arr[~np.isnan(arr)], 1) == 0))
    return gmin, integral


def _check_dataset(dataset_id: str) -> list[str]:
    """Run all live-data checks for one dataset, returning a list of failures."""
    manifest = load_manifest(dataset_id)
    adata = _load_adata(dataset_id)
    obs = adata.obs
    errs: list[str] = []

    # Some datasets keep clinical metadata in a separate table joined at runtime
    # (metadata_source.embedded == False, e.g. TCGA's Xena clinicalMatrix).
    # Those columns are not in the base h5ad, so obs-dependent checks can only be
    # validated post-join — skip them here and rely on the join tool's own checks.
    embedded = bool(manifest.metadata_source.get("embedded", False))

    # 1. declared metadata columns exist in obs (embedded metadata only)
    for col_name, col_def in (manifest.metadata_columns.items() if embedded else []):
        if col_name not in obs.columns:
            errs.append(f"metadata_columns['{col_name}'] not found in obs")
            continue

        # 2. allowed_values cover real values (∪ missing_values)
        allowed = col_def.allowed_values if isinstance(col_def, MetadataColumnDef) else []
        missing = col_def.missing_values if isinstance(col_def, MetadataColumnDef) else []
        if allowed:
            real = _obs_canon_values(obs[col_name])
            permitted = {_canon(v) for v in allowed} | {_canon(v) for v in missing}
            unexpected = real - permitted
            if unexpected:
                errs.append(
                    f"obs['{col_name}'] has values not in allowed_values "
                    f"or missing_values: {sorted(str(v) for _, v in unexpected)}"
                )

    # 3. feature_id_type vs var.index
    idx = adata.var.index.astype(str)
    n = len(idx)
    if n == 0:
        errs.append("var.index is empty")
    else:
        ft = manifest.feature_id_type
        if ft == "gene_symbol":
            frac_alpha = np.mean([s[:1].isalpha() for s in idx])
            if frac_alpha < 0.5:
                errs.append(
                    f"feature_id_type=gene_symbol but only {frac_alpha:.0%} of "
                    f"var.index entries start with a letter"
                )
        elif ft == "ensembl_gene_id":
            frac_ens = np.mean([s.startswith("ENSG") for s in idx])
            if frac_ens < 0.5:
                errs.append(
                    f"feature_id_type=ensembl_gene_id but only {frac_ens:.0%} of "
                    f"var.index entries start with ENSG"
                )
        # probe_id / entrez_id: platform-specific formats, left lenient.

    # 4. data_level range sanity (raw_counts only; others have documented scales)
    if manifest.data_level == "raw_counts" and dataset_id not in _DATA_LEVEL_RANGE_EXEMPT:
        gmin, integral = _x_min_and_integral(adata)
        if gmin < 0:
            errs.append(f"data_level=raw_counts but X has negative values (min={gmin})")
        if not integral:
            errs.append("data_level=raw_counts but X has non-integer values")

    # 5. Filters/contrasts/survival reference obs columns — only validatable on
    #    the base h5ad when metadata is embedded (else they apply post-join).
    if embedded:
        # 5a. default_sample_filter evaluates
        if manifest.default_sample_filter:
            try:
                obs.query(manifest.default_sample_filter)
            except Exception as exc:  # noqa: BLE001
                errs.append(f"default_sample_filter does not evaluate: {exc!r}")

        # 5b. default_contrasts subset_query evaluates + design_factor exists
        for i, c in enumerate(manifest.default_contrasts):
            df = c.get("design_factor")
            if df and df not in obs.columns:
                errs.append(f"default_contrasts[{i}].design_factor '{df}' not in obs")
            sq = c.get("subset_query")
            if sq:
                try:
                    obs.query(sq)
                except Exception as exc:  # noqa: BLE001
                    errs.append(f"default_contrasts[{i}].subset_query does not evaluate: {exc!r}")

        # 5c. survival columns exist when declared
        sc = manifest.survival_columns or {}
        for key in ("event_column", "time_column"):
            col = sc.get(key)
            if col and col not in obs.columns:
                errs.append(f"survival_columns.{key} '{col}' not in obs")

    # 6. curated_sample_list present among loaded samples
    if manifest.curated_sample_list:
        ids = set(obs.index.astype(str))
        if manifest.sample_id_column and manifest.sample_id_column in obs.columns:
            ids |= set(obs[manifest.sample_id_column].astype(str))
        present = sum(
            1 for b in manifest.curated_sample_list
            if b in ids or any(s.startswith(b) for s in ids)
        )
        frac = present / len(manifest.curated_sample_list)
        if frac < 0.9:
            errs.append(
                f"curated_sample_list: only {present}/{len(manifest.curated_sample_list)} "
                f"({frac:.0%}) barcodes found in loaded samples"
            )

    return errs


# --- Tests -------------------------------------------------------------------

_ALL_DATASETS = sorted(get_registry().list())


@pytest.mark.parametrize("dataset_id", _ALL_DATASETS)
def test_manifest_matches_live_data(dataset_id):
    """Manifest declarations hold against the real h5ad for each dataset."""
    errors = _check_dataset(dataset_id)
    assert not errors, f"{dataset_id} live-data mismatches:\n" + "\n".join(
        f"  - {e}" for e in errors
    )
