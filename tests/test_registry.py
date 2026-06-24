"""
Smoke tests for the biodata_registry package.

These tests verify the core registry functionality works end-to-end
without requiring any network access or external dependencies.
"""

import pytest

from biodata_registry import get_registry, load_manifest, list_available_datasets
from biodata_registry.registry import DatasetRegistry
from biodata_registry.manifest_schema import DatasetManifest, ManifestValidationResult


# ---------------------------------------------------------------------------
# Registry construction
# ---------------------------------------------------------------------------

def test_get_registry_returns_dataset_registry():
    """get_registry() returns a DatasetRegistry instance."""
    reg = get_registry()
    assert isinstance(reg, DatasetRegistry)


def test_get_registry_is_singleton():
    """Multiple calls to get_registry() return the same object."""
    reg1 = get_registry()
    reg2 = get_registry()
    assert reg1 is reg2


# ---------------------------------------------------------------------------
# Dataset discovery
# ---------------------------------------------------------------------------

def test_list_available_datasets_includes_moffitt():
    """list_available_datasets() includes gse71729_moffitt."""
    datasets = list_available_datasets()
    ids = [d["dataset_id"] for d in datasets]
    assert "gse71729_moffitt" in ids


def test_list_available_datasets_returns_at_least_one():
    """list_available_datasets() returns at least one dataset."""
    datasets = list_available_datasets()
    assert len(datasets) >= 1


def test_registry_list_includes_moffitt():
    """Registry.list() includes gse71729_moffitt."""
    reg = get_registry()
    assert "gse71729_moffitt" in reg.list()


def test_registry_contains_moffitt():
    """'gse71729_moffitt' in registry."""
    reg = get_registry()
    assert "gse71729_moffitt" in reg


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------

def test_load_manifest_returns_dataset_manifest():
    """load_manifest() returns a DatasetManifest."""
    manifest = load_manifest("gse71729_moffitt")
    assert isinstance(manifest, DatasetManifest)


def test_load_manifest_correct_dataset_id():
    """Loaded manifest has the correct dataset_id."""
    manifest = load_manifest("gse71729_moffitt")
    assert manifest.dataset_id == "gse71729_moffitt"


def test_load_manifest_correct_organism():
    """Moffitt manifest organism is 'human'."""
    manifest = load_manifest("gse71729_moffitt")
    assert manifest.organism == "human"


def test_load_manifest_correct_modality():
    """Moffitt manifest modality is 'bulk_microarray'."""
    manifest = load_manifest("gse71729_moffitt")
    assert manifest.modality == "bulk_microarray"


def test_load_manifest_analysis_path_b():
    """Moffitt manifest analysis_path is 'B' (log_expression → not raw_counts)."""
    manifest = load_manifest("gse71729_moffitt")
    assert manifest.analysis_path == "B"


def test_load_manifest_has_group_columns():
    """Moffitt manifest has at least one group column."""
    manifest = load_manifest("gse71729_moffitt")
    assert len(manifest.group_columns) >= 1


def test_load_manifest_has_limitations():
    """Moffitt manifest has at least one limitation."""
    manifest = load_manifest("gse71729_moffitt")
    assert len(manifest.limitations) >= 1


def test_load_manifest_has_default_contrasts():
    """Moffitt manifest has default contrasts defined."""
    manifest = load_manifest("gse71729_moffitt")
    assert len(manifest.default_contrasts) >= 1


# ---------------------------------------------------------------------------
# Manifest validation
# ---------------------------------------------------------------------------

def test_moffitt_manifest_is_valid():
    """Moffitt manifest passes schema validation."""
    manifest = load_manifest("gse71729_moffitt")
    result = manifest.validate()
    assert isinstance(result, ManifestValidationResult)
    assert result.valid, f"Validation errors: {result.errors}"


def test_all_manifests_validate():
    """Every registered manifest passes schema validation (no errors)."""
    reg = get_registry()
    failures = {}
    for dataset_id in reg.list():
        result = load_manifest(dataset_id).validate()
        if not result.valid:
            failures[dataset_id] = result.errors
    assert not failures, f"Manifests with validation errors: {failures}"


# ---------------------------------------------------------------------------
# Raw registry access
# ---------------------------------------------------------------------------

def test_registry_get_returns_dict():
    """registry.get() returns a dict for a known dataset_id."""
    reg = get_registry()
    raw = reg.get("gse71729_moffitt")
    assert isinstance(raw, dict)
    assert raw["dataset_id"] == "gse71729_moffitt"


def test_registry_get_unknown_returns_none():
    """registry.get() returns None for an unknown dataset_id."""
    reg = get_registry()
    assert reg.get("nonexistent_dataset_xyz") is None


def test_load_manifest_unknown_raises_key_error():
    """load_manifest() raises KeyError for an unknown dataset_id."""
    with pytest.raises(KeyError, match="not found in registry"):
        load_manifest("nonexistent_dataset_xyz")


# ---------------------------------------------------------------------------
# list_available_datasets entry shape
# ---------------------------------------------------------------------------

def test_list_available_datasets_entry_shape():
    """Each entry from list_available_datasets() has the expected keys."""
    datasets = list_available_datasets()
    required_keys = {"dataset_id", "title", "accession", "organism", "modality"}
    for entry in datasets:
        assert required_keys.issubset(entry.keys()), (
            f"Entry missing keys: {required_keys - entry.keys()}"
        )


# ---------------------------------------------------------------------------
# cohort_id / variant (same-cohort sibling variants)
# ---------------------------------------------------------------------------

def test_cohort_id_variant_round_trip():
    """cohort_id/variant survive from_dict -> to_dict; absent -> empty strings."""
    base = load_manifest("gse71729_moffitt").to_dict()
    assert base["cohort_id"] == ""        # standalone cohort defaults to ""
    assert base["variant"] == ""

    base["cohort_id"] = "demo_cohort"
    base["variant"] = "tpm"
    rt = DatasetManifest.from_dict(base).to_dict()
    assert rt["cohort_id"] == "demo_cohort"
    assert rt["variant"] == "tpm"


def test_gse205154_trio_share_cohort_id():
    """The three GSE205154 manifests declare the same cohort_id and distinct
    variants — the registry-level record of 'same samples, different units'."""
    ids = ["gse205154_sears", "gse205154_sears_counts", "gse205154_sears_tmm"]
    manifests = [load_manifest(d) for d in ids]
    assert {m.cohort_id for m in manifests} == {"gse205154"}
    assert {m.variant for m in manifests} == {"tpm", "counts", "tmm"}


def test_list_available_datasets_exposes_cohort_id():
    """list_available_datasets() surfaces cohort_id so the agent can see the
    sibling relationship without loading each manifest."""
    by_id = {d["dataset_id"]: d for d in list_available_datasets()}
    assert by_id["gse205154_sears"]["cohort_id"] == "gse205154"
    assert by_id["gse205154_sears"]["variant"] == "tpm"
    # a standalone dataset reports an empty cohort_id
    assert by_id["gse71729_moffitt"]["cohort_id"] == ""
