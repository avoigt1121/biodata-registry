"""
biodata_registry — Dataset manifest registry for bioinformatics agents.

This package provides a dataset-agnostic interface for loading, validating,
and querying biological dataset manifests.

Architecture
------------
manifests/
    YAML files describing each dataset (one file per dataset).
    All dataset-specific knowledge lives here: source URL, data type,
    condition columns, expected sample counts, contrast definitions, etc.

registry.py
    Discovers and indexes manifests by dataset_id.  The single source
    of truth for "which datasets exist."  Adding a new dataset means
    dropping a YAML file into manifests/ — no code changes required.

manifest_schema.py
    Validates manifest structure and provides typed access to manifest
    fields.  Keeps the schema in one authoritative place.

server.py
    FastMCP server exposing registry tools over MCP.
    Run with: python -m biodata_registry.server

Adding a new dataset
--------------------
1. Create biodata_registry/manifests/<dataset_id>.yaml following the schema.
2. The registry auto-discovers it on next import.
3. Run tests/test_registry.py to verify.
"""

from .registry import DatasetRegistry, load_manifest, list_available_datasets
from .integration import get_integration_plan

_registry = None


def get_registry() -> DatasetRegistry:
    """Return the module-level registry singleton, creating it on first call."""
    global _registry
    if _registry is None:
        _registry = DatasetRegistry()
    return _registry


__all__ = [
    "DatasetRegistry",
    "get_registry",
    "load_manifest",
    "list_available_datasets",
    "get_integration_plan",
]
