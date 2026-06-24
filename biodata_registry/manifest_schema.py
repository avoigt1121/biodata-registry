"""
Dataset manifest schema: typed contract for all datasets in the registry.

DatasetManifest is the single authoritative type for dataset metadata.
Construct one from a YAML dict via DatasetManifest.from_dict(d), then
call manifest.validate() before using it in any analysis.

Field reference
---------------
Required
~~~~~~~~
dataset_id        str   Unique snake_case key matching the YAML filename.
title             str   Full display title.
accession         str   Primary accession ID (GEO, CPTAC, etc.).
organism          str   One of VALID_ORGANISMS.
modality          str   One of VALID_MODALITIES.
platform          str   Array/sequencing platform name (free text).
data_level        str   One of VALID_DATA_LEVELS. Determines analysis_path.
feature_id_type   str   One of VALID_FEATURE_ID_TYPES.
expression_source dict  {type: <source_type>, url: ..., format: ...,
                        collapsed_url: optional, only for feature_mapping.
                        requires_collapse=true datasets. URL to a precomputed
                        h5ad with probes already collapsed to gene symbols via
                        collapse_method. When set, _build_loading_plan
                        (DecoupleRpy_Agent) loads this directly and skips the
                        decoupler_collapse_probes_to_genes step.}
metadata_source   dict  {type: <source_type>, embedded: bool, ...}
sample_id_column  str   Column in obs that uniquely identifies samples.
group_columns     list  Obs columns usable for grouping or DE.
valid_workflows   list  Subset of VALID_WORKFLOWS.
limitations       list  Known caveats; must be non-empty (honest reporting).

Optional
~~~~~~~~
cohort_id         str   Shared identifier for datasets that are the SAME samples
                        quantified/normalized different ways (sibling variants,
                        e.g. the GSE205154 TPM/counts/TMM trio). Datasets that
                        share a cohort_id must never be pooled or meta-analyzed
                        (that double-counts the cohort); the only valid
                        cross-variant operation is a normalization concordance
                        check. Empty string = standalone cohort. Drives the
                        same-cohort gate in integration.get_integration_plan.
variant           str   Free-text label for which quantification this is within
                        its cohort_id (e.g. "tpm", "counts", "tmm"). Used for
                        report labelling; only meaningful alongside cohort_id.
feature_mapping   dict  Probe→gene collapse params. Required when
                        feature_id_type='probe_id'.
                        {requires_collapse, gene_symbol_column,
                         collapse_method, multi_gene_policy}
survival_columns  dict  {event_column, time_column} — None values are fine.
default_contrasts list  [{design_factor, test_group, control_group, method}]
description       str   One-sentence plain-language summary.
preprocessing     str   Plain-language provenance: what the raw data was, what
                        normalization/transform/units, feature-ID handling, and
                        any curation/subsetting applied to produce the hosted data.
publication       dict  {doi, authors, year, journal, title}

Derived (not stored)
~~~~~~~~~~~~~~~~~~~~
analysis_path     "A" if data_level='raw_counts', else "B".
                  "A" → DESeq2 pipeline.
                  "B" → skip preprocess_data, use ttest or limma.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Controlled vocabularies
# ---------------------------------------------------------------------------

VALID_ORGANISMS = frozenset({"human", "mouse"})

VALID_MODALITIES = frozenset({
    "bulk_microarray",   # Agilent, Affymetrix single- or two-color
    "bulk_rnaseq",       # bulk RNA-seq (raw or normalised)
    "sc_rnaseq",         # single-cell RNA-seq
    "spatial_rnaseq",    # spatial transcriptomics (e.g. 10x Visium)
    "proteomics",        # mass spec / CPTAC-style
})

VALID_DATA_LEVELS = frozenset({
    "raw_counts",        # integer UMI or read counts → Path A (DESeq2)
    "log_expression",    # log2-normalised intensity (single-channel array, log-CPM)
    "log_ratio",         # log2 ratio (two-color array, log-RPKM)
    "normalized",        # pre-normalised, exact scale unspecified → Path B
    "tpm",               # TPM values → Path B
    "fpkm",              # FPKM values → Path B
    "protein_abundance", # proteomics normalised abundance
})

# data_levels that map to Path A (raw counts → DESeq2)
_PATH_A_LEVELS = frozenset({"raw_counts"})

VALID_FEATURE_ID_TYPES = frozenset({
    "probe_id",          # microarray probe IDs (require collapse to gene symbols)
    "gene_symbol",       # HGNC gene symbols
    "ensembl_gene_id",   # Ensembl gene IDs
    "entrez_id",         # NCBI Entrez IDs
    "protein_id",        # UniProt / RefSeq protein IDs
})

VALID_EXPRESSION_SOURCE_TYPES = frozenset({
    "geo_series_matrix", # NCBI GEO series matrix (.txt / .txt.gz)
    "geo_soft",          # GEO SOFT format
    "url",               # direct download URL
    "local",             # local file path (testing / offline use)
    "cptac",             # CPTAC data portal
})

VALID_METADATA_SOURCE_TYPES = frozenset({
    "geo_series_matrix",    # sample chars embedded in series matrix header
    "supplementary_table",  # separate supplementary file
    "local",                # local file
    "manual",               # manually curated mapping
})

VALID_WORKFLOWS = frozenset({
    "microarray",
    "activity_scoring",
    "activity_stats",
    "survival",
})

VALID_DE_METHODS = frozenset({"deseq2", "ttest", "limma"})

VALID_COLLAPSE_METHODS = frozenset({"mean", "max", "most_variable"})

VALID_COLUMN_ROLES = frozenset({
    "primary_condition",   # main grouping variable for DE / comparison
    "secondary_condition", # additional biologically meaningful grouping
    "sample_origin",       # tissue / cell-type metadata (group with caution)
    "technical_metadata",  # quality / processing metadata — no biological grouping
})


# ---------------------------------------------------------------------------
# MetadataColumnDef — typed semantic definition for one obs column
# ---------------------------------------------------------------------------

@dataclass
class MetadataColumnDef:
    """
    Semantic contract for a single metadata column.

    Defines what values are biologically meaningful, what counts as missing,
    how to interpret empty values, and what analyses are allowed or refused.
    """

    role: str
    biological_grouping_allowed: bool = True
    allowed_values: list[str] = field(default_factory=list)
    missing_values: list[str] = field(default_factory=list)
    empty_value_meaning: str = ""
    code_map: dict[str, str] = field(default_factory=dict)
    source_column: Optional[str] = None
    decoded_column: Optional[str] = None
    interpretation_warning: str = ""
    reporting_rules: list[str] = field(default_factory=list)
    refusal_rules: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "MetadataColumnDef":
        return cls(
            role=str(d.get("role", "sample_origin")),
            biological_grouping_allowed=bool(d.get("biological_grouping_allowed", True)),
            allowed_values=list(d.get("allowed_values") or []),
            missing_values=list(d.get("missing_values") or []),
            empty_value_meaning=str(d.get("empty_value_meaning") or ""),
            code_map={str(k): str(v) for k, v in (d.get("code_map") or {}).items()},
            source_column=str(d["source_column"]) if d.get("source_column") else None,
            decoded_column=str(d["decoded_column"]) if d.get("decoded_column") else None,
            interpretation_warning=str(d.get("interpretation_warning") or ""),
            reporting_rules=list(d.get("reporting_rules") or []),
            refusal_rules=list(d.get("refusal_rules") or []),
        )

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "biological_grouping_allowed": self.biological_grouping_allowed,
            "allowed_values": self.allowed_values,
            "missing_values": self.missing_values,
            "empty_value_meaning": self.empty_value_meaning,
            "code_map": self.code_map,
            "source_column": self.source_column,
            "decoded_column": self.decoded_column,
            "interpretation_warning": self.interpretation_warning,
            "reporting_rules": self.reporting_rules,
            "refusal_rules": self.refusal_rules,
        }


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------

@dataclass
class ManifestValidationResult:
    """Outcome of DatasetManifest.validate() or validate_manifest()."""
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def __str__(self) -> str:
        lines = [f"valid={self.valid}"]
        for e in self.errors:
            lines.append(f"  ERROR: {e}")
        for w in self.warnings:
            lines.append(f"  WARN:  {w}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Typed manifest
# ---------------------------------------------------------------------------

@dataclass
class DatasetManifest:
    """
    Typed contract for a dataset manifest.

    Construct via DatasetManifest.from_dict(yaml_dict).
    Validate via manifest.validate() before use.
    The analysis_path property is derived from data_level — do not store it.
    """

    # Required: identity
    dataset_id: str
    title: str
    accession: str
    organism: str

    # Required: data characteristics
    modality: str
    platform: str
    data_level: str
    feature_id_type: str

    # Required: data access
    expression_source: dict
    metadata_source: dict

    # Required: analysis metadata
    group_columns: list[str]
    valid_workflows: list[str]
    limitations: list[str]

    # Optional: same-cohort sibling grouping. Datasets sharing a cohort_id are the
    # SAME samples in different quantifications/units (e.g. TPM vs TMM vs counts).
    # They must never be pooled or meta-analyzed — see integration.py's same-cohort
    # gate, which routes such requests to a concordance check instead.
    cohort_id: str = ""
    variant: str = ""   # quantification label within the cohort ("tpm"/"counts"/"tmm"/...)

    # Optional: sample ID column (None = use obs DataFrame index)
    sample_id_column: Optional[str] = None

    # Optional: feature-to-gene mapping
    # Required in practice when feature_id_type='probe_id'.
    feature_mapping: dict = field(default_factory=dict)

    # Optional: survival analysis endpoints
    survival_columns: dict = field(default_factory=dict)

    # Optional: default DE contrasts
    default_contrasts: list[dict] = field(default_factory=list)

    # Optional: metadata column semantic definitions
    metadata_columns: dict = field(default_factory=dict)   # str → MetadataColumnDef

    # Optional: dataset-level reporting and refusal rules
    reporting_rules: list[str] = field(default_factory=list)
    refusal_rules: list[str] = field(default_factory=list)

    # Optional: display / citation
    description: str = ""
    # Optional: plain-language provenance / how the hosted data was prepared
    preprocessing: str = ""
    publication: dict = field(default_factory=dict)

    # Optional: proactive data-quality disclaimer shown at load time
    dataset_disclaimer: str = ""

    # Optional: curated sample list — TCGA barcodes (16-char submitter_id format)
    # confirming the samples are the target tissue type.  When non-empty, the
    # loading plan inserts a filter step before any analysis.
    curated_sample_list: list[str] = field(default_factory=list)
    curated_sample_source: str = ""   # citation / description of where the list came from

    # Optional: pandas query string applied before any analysis when the dataset
    # contains mixed sample types (e.g. cell lines + primary tumors).
    # Applied as adata.obs.query(default_sample_filter) at load time.
    # Empty string = no filter.
    default_sample_filter: str = ""
    default_sample_filter_note: str = ""  # human-readable explanation of why the filter exists

    @property
    def analysis_path(self) -> str:
        """
        Derived from data_level.

        'A' — raw_counts; use DESeq2 pipeline.
        'B' — all other levels; skip preprocess_data, use ttest or limma.
        """
        return "A" if self.data_level in _PATH_A_LEVELS else "B"

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    @classmethod
    def from_dict(cls, d: dict) -> "DatasetManifest":
        """
        Construct a DatasetManifest from a parsed YAML dict.

        Raises ValueError listing all missing required fields.
        Does not validate controlled vocabularies — call validate() for that.
        """
        required = [
            "dataset_id", "title", "accession", "organism",
            "modality", "platform", "data_level", "feature_id_type",
            "expression_source", "metadata_source",
            "group_columns", "valid_workflows", "limitations",
        ]
        missing = [f for f in required if f not in d or d[f] is None]
        if missing:
            raise ValueError(
                f"Manifest is missing required fields: {missing}"
            )

        return cls(
            dataset_id=str(d["dataset_id"]),
            title=str(d["title"]),
            accession=str(d["accession"]),
            organism=str(d["organism"]),
            modality=str(d["modality"]),
            platform=str(d["platform"]),
            data_level=str(d["data_level"]),
            feature_id_type=str(d["feature_id_type"]),
            expression_source=dict(d["expression_source"]),
            metadata_source=dict(d["metadata_source"]),
            cohort_id=str(d.get("cohort_id") or ""),
            variant=str(d.get("variant") or ""),
            sample_id_column=str(d["sample_id_column"]) if d.get("sample_id_column") else None,
            group_columns=list(d["group_columns"]),
            valid_workflows=list(d["valid_workflows"]),
            limitations=list(d["limitations"]),
            feature_mapping=dict(d.get("feature_mapping") or {}),
            survival_columns=dict(d.get("survival_columns") or {}),
            default_contrasts=list(d.get("default_contrasts") or []),
            metadata_columns={
                col_name: MetadataColumnDef.from_dict(col_def)
                for col_name, col_def in (d.get("metadata_columns") or {}).items()
            },
            reporting_rules=list(d.get("reporting_rules") or []),
            refusal_rules=list(d.get("refusal_rules") or []),
            description=str(d.get("description") or ""),
            preprocessing=str(d.get("preprocessing") or ""),
            publication=dict(d.get("publication") or {}),
            dataset_disclaimer=str(d.get("dataset_disclaimer") or ""),
            curated_sample_list=list(d.get("curated_sample_list") or []),
            curated_sample_source=str(d.get("curated_sample_source") or ""),
            default_sample_filter=str(d.get("default_sample_filter") or ""),
            default_sample_filter_note=str(d.get("default_sample_filter_note") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serialisable dict of all fields."""
        return {
            "dataset_id": self.dataset_id,
            "title": self.title,
            "accession": self.accession,
            "organism": self.organism,
            "modality": self.modality,
            "platform": self.platform,
            "data_level": self.data_level,
            "feature_id_type": self.feature_id_type,
            "analysis_path": self.analysis_path,
            "expression_source": self.expression_source,
            "metadata_source": self.metadata_source,
            "cohort_id": self.cohort_id,
            "variant": self.variant,
            "sample_id_column": self.sample_id_column,
            "group_columns": self.group_columns,
            "valid_workflows": self.valid_workflows,
            "limitations": self.limitations,
            "feature_mapping": self.feature_mapping,
            "survival_columns": self.survival_columns,
            "default_contrasts": self.default_contrasts,
            "metadata_columns": {
                k: v.to_dict() if isinstance(v, MetadataColumnDef) else v
                for k, v in self.metadata_columns.items()
            },
            "reporting_rules": self.reporting_rules,
            "refusal_rules": self.refusal_rules,
            "description": self.description,
            "preprocessing": self.preprocessing,
            "publication": self.publication,
            "dataset_disclaimer": self.dataset_disclaimer,
            "curated_sample_list": self.curated_sample_list,
            "curated_sample_source": self.curated_sample_source,
            "default_sample_filter": self.default_sample_filter,
            "default_sample_filter_note": self.default_sample_filter_note,
        }

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> ManifestValidationResult:
        """
        Validate this manifest against the schema.

        Checks controlled vocabularies, required non-empty fields, and
        logical consistency (e.g. probe_id implies feature_mapping).
        Returns ManifestValidationResult — does not raise.
        """
        errors: list[str] = []
        warnings: list[str] = []
        self._check_required_fields(errors)
        self._check_vocabularies(errors)
        self._check_expression_source(errors, warnings)
        self._check_metadata_source(errors, warnings)
        self._check_groups_workflows_limitations(errors, warnings)
        self._check_feature_mapping(warnings)
        self._check_metadata_columns(warnings)
        self._check_default_contrasts(warnings)
        return ManifestValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    # ── validate() helpers (one concern each) ────────────────────────────
    def _check_required_fields(self, errors: list[str]) -> None:
        for fname in [
            "dataset_id", "title", "accession", "organism",
            "modality", "platform", "data_level", "feature_id_type",
        ]:
            if not str(getattr(self, fname, "")).strip():
                errors.append(f"'{fname}' must be a non-empty string")

    def _check_vocabularies(self, errors: list[str]) -> None:
        if self.organism not in VALID_ORGANISMS:
            errors.append(
                f"organism '{self.organism}' not in {sorted(VALID_ORGANISMS)}"
            )
        if self.modality not in VALID_MODALITIES:
            errors.append(
                f"modality '{self.modality}' not in {sorted(VALID_MODALITIES)}"
            )
        if self.data_level not in VALID_DATA_LEVELS:
            errors.append(
                f"data_level '{self.data_level}' not in {sorted(VALID_DATA_LEVELS)}"
            )
        if self.feature_id_type not in VALID_FEATURE_ID_TYPES:
            errors.append(
                f"feature_id_type '{self.feature_id_type}' not in "
                f"{sorted(VALID_FEATURE_ID_TYPES)}"
            )

    def _check_expression_source(self, errors: list[str], warnings: list[str]) -> None:
        src_type = self.expression_source.get("type")
        if not src_type:
            errors.append("expression_source.type is required")
        elif src_type not in VALID_EXPRESSION_SOURCE_TYPES:
            warnings.append(
                f"expression_source.type '{src_type}' not in "
                f"{sorted(VALID_EXPRESSION_SOURCE_TYPES)}"
            )
        if src_type in {"geo_series_matrix", "url", "cptac"} and not self.expression_source.get("url"):
            warnings.append(
                "expression_source.url is not set — "
                "agent cannot auto-download this dataset"
            )

    def _check_metadata_source(self, errors: list[str], warnings: list[str]) -> None:
        meta_type = self.metadata_source.get("type")
        if not meta_type:
            errors.append("metadata_source.type is required")
        elif meta_type not in VALID_METADATA_SOURCE_TYPES:
            warnings.append(
                f"metadata_source.type '{meta_type}' not in "
                f"{sorted(VALID_METADATA_SOURCE_TYPES)}"
            )

    def _check_groups_workflows_limitations(
        self, errors: list[str], warnings: list[str]
    ) -> None:
        if not self.group_columns:
            if "survival" in self.valid_workflows:
                # Survival-only cohorts (e.g. a single-condition tumor series with
                # outcome data) legitimately have no DE grouping column.
                warnings.append(
                    "group_columns is empty — permitted because 'survival' is a "
                    "valid_workflow (no differential-expression grouping column)"
                )
            else:
                errors.append("group_columns must have at least one entry")

        # valid_workflows
        if not self.valid_workflows:
            warnings.append("valid_workflows is empty")
        unknown_wf = set(self.valid_workflows) - VALID_WORKFLOWS
        if unknown_wf:
            warnings.append(
                f"Unknown workflow(s): {sorted(unknown_wf)} — will be ignored"
            )

        # limitations
        if not self.limitations:
            warnings.append(
                "limitations is empty — add at least one known caveat "
                "for honest reporting"
            )

    def _check_feature_mapping(self, warnings: list[str]) -> None:
        if self.feature_id_type == "probe_id":
            if not self.feature_mapping.get("requires_collapse"):
                warnings.append(
                    "feature_id_type='probe_id' but feature_mapping.requires_collapse "
                    "is not set — enrichment tools require gene symbols"
                )
            method = self.feature_mapping.get("collapse_method")
            if method and method not in VALID_COLLAPSE_METHODS:
                warnings.append(
                    f"feature_mapping.collapse_method '{method}' not in "
                    f"{sorted(VALID_COLLAPSE_METHODS)}"
                )

    def _check_metadata_columns(self, warnings: list[str]) -> None:
        for col_name, col_def in self.metadata_columns.items():
            role = col_def.role if isinstance(col_def, MetadataColumnDef) else col_def.get("role", "")
            bio_ok = (col_def.biological_grouping_allowed if isinstance(col_def, MetadataColumnDef)
                      else col_def.get("biological_grouping_allowed", True))
            if role not in VALID_COLUMN_ROLES:
                warnings.append(
                    f"metadata_columns['{col_name}'].role '{role}' "
                    f"not in {sorted(VALID_COLUMN_ROLES)}"
                )
            if not bio_ok and col_name in self.group_columns:
                warnings.append(
                    f"metadata_columns['{col_name}'].biological_grouping_allowed=False "
                    f"but '{col_name}' appears in group_columns"
                )

    def _check_default_contrasts(self, warnings: list[str]) -> None:
        for i, contrast in enumerate(self.default_contrasts):
            method = contrast.get("method")
            if method and method not in VALID_DE_METHODS:
                warnings.append(
                    f"default_contrasts[{i}].method '{method}' not in "
                    f"{sorted(VALID_DE_METHODS)}"
                )
            if self.analysis_path == "B" and method == "deseq2":
                warnings.append(
                    f"default_contrasts[{i}].method='deseq2' on a Path B dataset "
                    f"(data_level='{self.data_level}') — DESeq2 requires raw integer counts"
                )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def validate_manifest(manifest: "dict | DatasetManifest") -> ManifestValidationResult:
    """
    Validate a manifest dict or DatasetManifest instance.

    Accepts both forms so callers do not need to construct DatasetManifest
    explicitly before checking validity.
    """
    if isinstance(manifest, DatasetManifest):
        return manifest.validate()
    if not isinstance(manifest, dict):
        return ManifestValidationResult(
            valid=False,
            errors=["manifest must be a dict or DatasetManifest"],
        )
    try:
        dm = DatasetManifest.from_dict(manifest)
        return dm.validate()
    except ValueError as exc:
        return ManifestValidationResult(valid=False, errors=[str(exc)])


def require_valid(manifest: "dict | DatasetManifest") -> "dict | DatasetManifest":
    """
    Validate and raise ValueError if invalid.

    Returns the manifest unchanged for use in chained calls.
    """
    result = validate_manifest(manifest)
    if not result.valid:
        dataset_id = (
            manifest.dataset_id
            if isinstance(manifest, DatasetManifest)
            else manifest.get("dataset_id", "?")
        )
        raise ValueError(
            f"Invalid manifest for '{dataset_id}':\n"
            + "\n".join(f"  - {e}" for e in result.errors)
        )
    return manifest
