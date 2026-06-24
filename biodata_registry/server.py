"""
FastMCP server for the biodata_registry package.

Exposes registry tools over MCP so agent processes can query dataset metadata
without importing this package directly.

Run with:
    python -m biodata_registry.server

Tools exposed
-------------
list_datasets()
    List all registered dataset IDs with their title and modality.

get_manifest(dataset_id)
    Return the full manifest dict for a dataset.

get_prohibited_inferences(dataset_id)
    Return the refusal_rules list from a manifest — i.e. what an agent
    must not infer or claim about this dataset.

get_contrast_definition(dataset_id, column)
    Return all default contrast definitions for a specific design_factor column.

get_integration_plan(dataset_ids, design_factor=None, test_group=None,
                     control_group=None)
    Decide whether multiple datasets can be combined early (pool expression),
    late (meta-analyze results), or refused — a pure function of manifest
    metadata.
"""

from __future__ import annotations

from typing import Any, Optional

from fastmcp import FastMCP

from .integration import get_integration_plan as _get_integration_plan
from .registry import get_registry, load_manifest, list_available_datasets

mcp = FastMCP("biodata-registry")


@mcp.tool()
def list_datasets() -> list[dict[str, str]]:
    """
    List all registered datasets.

    Returns a list of dicts, each containing:
      - dataset_id: unique identifier
      - title: display title
      - modality: data modality (e.g. bulk_microarray, bulk_rnaseq)
      - accession: primary accession (e.g. GEO series ID)
      - organism: organism (e.g. human, mouse)
    """
    return list_available_datasets()


@mcp.tool()
def get_manifest(dataset_id: str) -> dict[str, Any]:
    """
    Return the full manifest for a dataset as a dict.

    Parameters
    ----------
    dataset_id:
        The snake_case dataset identifier, e.g. "gse71729_moffitt".

    Returns
    -------
    Full manifest dict including all fields (expression_source,
    metadata_source, group_columns, default_contrasts, limitations, etc.).

    Raises
    ------
    ValueError if dataset_id is not registered.
    """
    reg = get_registry()
    raw = reg.get(dataset_id)
    if raw is None:
        available = reg.list()
        raise ValueError(
            f"Dataset '{dataset_id}' not found in registry. "
            f"Available datasets: {available}"
        )
    # Return the manifest as a serialisable dict via the typed object
    manifest = load_manifest(dataset_id)
    return manifest.to_dict()


@mcp.tool()
def get_prohibited_inferences(dataset_id: str) -> dict[str, Any]:
    """
    Return refusal rules for a dataset — things an agent must not claim.

    Returns both dataset-level refusal_rules and per-column refusal_rules
    from metadata_columns.

    Parameters
    ----------
    dataset_id:
        The snake_case dataset identifier, e.g. "gse71729_moffitt".

    Returns
    -------
    Dict with:
      - dataset_id: str
      - dataset_level_refusal_rules: list[str]
      - column_refusal_rules: dict[str, list[str]]  (column_name → rules)
    """
    manifest = load_manifest(dataset_id)
    column_refusals: dict[str, list[str]] = {}
    for col_name, col_def in manifest.metadata_columns.items():
        rules = col_def.refusal_rules if hasattr(col_def, "refusal_rules") else []
        if rules:
            column_refusals[col_name] = rules

    return {
        "dataset_id": dataset_id,
        "dataset_level_refusal_rules": manifest.refusal_rules,
        "column_refusal_rules": column_refusals,
    }


@mcp.tool()
def get_contrast_definition(dataset_id: str, column: str) -> dict[str, Any]:
    """
    Return default contrast definitions for a specific design_factor column.

    Parameters
    ----------
    dataset_id:
        The snake_case dataset identifier, e.g. "gse71729_moffitt".
    column:
        The obs column name to filter contrasts by design_factor,
        e.g. "tumor_subtype".

    Returns
    -------
    Dict with:
      - dataset_id: str
      - column: str
      - contrasts: list[dict]  — all contrasts where design_factor == column
      - column_metadata: dict  — semantic definition for the column (if defined)

    Raises
    ------
    ValueError if dataset_id is not registered.
    """
    manifest = load_manifest(dataset_id)

    contrasts = [
        c for c in manifest.default_contrasts
        if c.get("design_factor") == column
    ]

    col_def = manifest.metadata_columns.get(column)
    column_metadata = col_def.to_dict() if col_def is not None else {}

    return {
        "dataset_id": dataset_id,
        "column": column,
        "contrasts": contrasts,
        "column_metadata": column_metadata,
    }


@mcp.tool()
def get_integration_plan(
    dataset_ids: list[str],
    design_factor: Optional[str] = None,
    test_group: Optional[str] = None,
    control_group: Optional[str] = None,
) -> dict[str, Any]:
    """
    Decide how (or whether) multiple datasets can be combined.

    Pure function of manifest metadata — loads no expression data. Resolves the
    cross-dataset compatibility decision matrix (ADR-0001): organism / ortholog
    bridge, shared gene_symbol feature space, modality, data_level poolability,
    and metadata-level design confound.

    Parameters
    ----------
    dataset_ids:
        Two or more registered dataset identifiers. Fewer than two yields a
        refusal (NOT_MULTI).
    design_factor, test_group, control_group:
        Optional. The contrast the caller intends to run. When supplied, the
        confound gate refuses (CONFOUNDED_DESIGN) if metadata shows no single
        cohort can express both arms. When omitted, design separability is
        deferred to the specialist's runtime check.

    Sibling variants of one cohort (datasets sharing a ``cohort_id`` — the same
    samples in different quantifications) are detected first: requesting only a
    cohort's variants yields mode "concordance" (compare, don't combine);
    mixing them with other datasets refuses with DUPLICATE_COHORT.

    Returns
    -------
    Dict with:
      - mode: "early" | "late" | "concordance" | "refuse"
      - reason: str — human-readable, surfaced verbatim by the agent
      - shared_feature_space: str | None (e.g. "gene_symbol")
      - requires_ortholog_mapping: bool
      - requires_probe_collapse: bool
      - batch_key: str ("dataset_id")
      - poolable_data_level: str | None (the shared level when mode == "early")
      - per_dataset: list of {dataset_id, organism, modality, data_level,
        analysis_path, feature_id_type, requires_collapse, cohort_id, variant}
      - refusal_rules_triggered: list[str] — stable codes (NOT_MULTI,
        DUPLICATE_COHORT, CROSS_ORGANISM_NO_BRIDGE, NO_SHARED_FEATURE_SPACE,
        CROSS_MODALITY, CONFOUNDED_DESIGN)

    Raises
    ------
    ValueError if any dataset_id is not registered.
    """
    return _get_integration_plan(
        dataset_ids,
        design_factor=design_factor,
        test_group=test_group,
        control_group=control_group,
    )


if __name__ == "__main__":
    mcp.run()
