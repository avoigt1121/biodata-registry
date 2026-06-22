"""
Dataset registry: maps dataset_id strings to manifest file paths and
parsed manifest dicts/objects.

The registry auto-discovers all *.yaml files under the manifests/ directory
at import time.  Adding a new dataset requires only dropping a new YAML file
there — no code edits needed.

Usage
-----
    # Low-level: raw dict
    from biodata_registry import get_registry
    reg = get_registry()
    raw = reg.get("gse71729_moffitt")        # dict or None

    # High-level: typed manifest
    from biodata_registry.registry import load_manifest, list_available_datasets
    manifest = load_manifest("gse71729_moffitt")  # DatasetManifest or KeyError
    print(manifest.organism)
    print(list_available_datasets())

Design
------
All dataset-specific knowledge (URL, condition columns, data type) lives in
YAML manifests, not in this module.  The registry is intentionally thin:
it only knows where manifests are on disk and how to load them.
"""

import warnings
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import yaml

if TYPE_CHECKING:
    # Imported lazily at runtime (inside functions); declared here only so the
    # string annotations below resolve for type checkers and linters.
    from .manifest_schema import DatasetManifest, ManifestValidationResult

_MANIFEST_DIR = Path(__file__).parent / "manifests"


class DatasetRegistry:
    """
    Lightweight registry that indexes dataset manifests by dataset_id.

    Manifests are discovered from the manifests/ directory at construction
    time and cached after first parse.  Manual registration is also supported
    for testing or dynamic datasets.
    """

    def __init__(self, manifest_dir: Path = _MANIFEST_DIR):
        self._manifest_dir = manifest_dir
        self._index: dict[str, Path] = {}   # dataset_id → yaml path
        self._cache: dict[str, dict] = {}   # dataset_id → parsed dict
        self._discover()

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------

    def _discover(self) -> None:
        """Scan manifest_dir for *.yaml files and index them by dataset_id."""
        if not self._manifest_dir.exists():
            return
        for path in sorted(self._manifest_dir.glob("*.yaml")):
            try:
                with open(path, encoding="utf-8") as fh:
                    doc = yaml.safe_load(fh)
                dataset_id = doc.get("dataset_id") if isinstance(doc, dict) else None
                if dataset_id:
                    self._index[dataset_id] = path
                else:
                    warnings.warn(
                        f"Manifest {path.name} is missing 'dataset_id' — skipping."
                    )
            except Exception as exc:
                warnings.warn(f"Skipping malformed manifest {path.name}: {exc}")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, dataset_id: str) -> Optional[dict]:
        """
        Return the parsed manifest for dataset_id, or None if not found.

        Manifests are cached after first load.
        """
        if dataset_id not in self._index:
            return None
        if dataset_id not in self._cache:
            with open(self._index[dataset_id], encoding="utf-8") as fh:
                self._cache[dataset_id] = yaml.safe_load(fh)
        return self._cache[dataset_id]

    def list(self) -> list[str]:
        """Return a sorted list of all registered dataset_ids."""
        return sorted(self._index.keys())

    def describe(self, dataset_id: str) -> Optional[str]:
        """Return a one-line description for dataset_id, or None."""
        manifest = self.get(dataset_id)
        if manifest is None:
            return None
        return manifest.get("description", "(no description)")

    def register(self, dataset_id: str, manifest_path: Path) -> None:
        """
        Manually register a manifest file.

        Useful for testing or for datasets whose manifests live outside
        the default manifests/ directory.  Invalidates the cache for
        dataset_id if it was previously loaded.
        """
        self._index[dataset_id] = manifest_path
        self._cache.pop(dataset_id, None)

    def reload(self) -> None:
        """Re-scan the manifest directory and clear the cache."""
        self._index.clear()
        self._cache.clear()
        self._discover()

    # ------------------------------------------------------------------
    # Dunder helpers
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._index)

    def __contains__(self, dataset_id: str) -> bool:
        return dataset_id in self._index

    def __repr__(self) -> str:
        return f"DatasetRegistry({len(self)} datasets: {self.list()})"


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_registry: Optional[DatasetRegistry] = None


def get_registry() -> DatasetRegistry:
    """Return the module-level registry singleton, creating it on first call."""
    global _registry
    if _registry is None:
        _registry = DatasetRegistry()
    return _registry


# ---------------------------------------------------------------------------
# Module-level typed API
# ---------------------------------------------------------------------------

def load_manifest(dataset_id: str) -> "DatasetManifest":
    """
    Load a dataset manifest by ID and return a typed DatasetManifest.

    Parameters
    ----------
    dataset_id:
        The snake_case dataset identifier (e.g. "gse71729_moffitt").

    Returns
    -------
    DatasetManifest — fully typed, ready to use in workflow functions.

    Raises
    ------
    KeyError  if dataset_id is not registered.  Error message includes
              the list of available datasets so the caller knows their options.
    ValueError  if the manifest YAML is present but missing required fields.
    """
    from .manifest_schema import DatasetManifest

    registry = get_registry()
    raw = registry.get(dataset_id)
    if raw is None:
        available = registry.list()
        raise KeyError(
            f"Dataset '{dataset_id}' not found in registry. "
            f"Available datasets: {available}"
        )
    return DatasetManifest.from_dict(raw)


def list_available_datasets() -> list[dict]:
    """
    Return brief metadata for every registered dataset.

    Each entry has: dataset_id, title, accession, organism, modality.
    Use load_manifest(dataset_id) to get the full typed manifest.
    """
    registry = get_registry()
    results = []
    for did in registry.list():
        raw = registry.get(did) or {}
        results.append({
            "dataset_id": did,
            "title": raw.get("title") or raw.get("description", ""),
            "accession": raw.get("accession", ""),
            "organism": raw.get("organism", ""),
            "modality": raw.get("modality", ""),
            "preprocessing": raw.get("preprocessing", ""),
        })
    return results


def validate_manifest(manifest: "dict | DatasetManifest") -> "ManifestValidationResult":
    """
    Validate a manifest dict or DatasetManifest and return a result object.

    Thin wrapper around manifest_schema.validate_manifest() exposed here
    so callers can do everything through the registry module.
    """
    from .manifest_schema import validate_manifest as _validate
    return _validate(manifest)
