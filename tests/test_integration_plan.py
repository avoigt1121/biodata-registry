"""
Unit tests for the cross-dataset compatibility engine (ADR-0001 Phase 1, step 2).

``get_integration_plan`` / ``plan_for_manifests`` are pure functions of manifest
metadata, so these tests need no network and no data loading. Where convenient
they use real registered datasets (data_level / feature_id_type confirmed
against each manifest); the cases the 16-dataset registry cannot express —
equal ``normalized``, ``probe_id`` without collapse, cross-organism,
cross-modality, declared confound — use minimal constructed manifests.
"""

import pytest

from biodata_registry import get_integration_plan
from biodata_registry.integration import (
    CONCORDANCE,
    CONFOUNDED_DESIGN,
    CROSS_MODALITY,
    CROSS_ORGANISM_NO_BRIDGE,
    CROSS_RESOLUTION,
    DUPLICATE_COHORT,
    NO_SHARED_FEATURE_SPACE,
    NOT_MULTI,
    plan_for_manifests,
)
from biodata_registry.manifest_schema import DatasetManifest, MetadataColumnDef

PLAN_KEYS = {
    "mode",
    "reason",
    "shared_feature_space",
    "requires_ortholog_mapping",
    "requires_probe_collapse",
    "batch_key",
    "poolable_data_level",
    "per_dataset",
    "refusal_rules_triggered",
}
PER_DATASET_KEYS = {
    "dataset_id",
    "organism",
    "modality",
    "data_level",
    "analysis_path",
    "feature_id_type",
    "requires_collapse",
    "cohort_id",
    "variant",
}


# ---------------------------------------------------------------------------
# Synthetic manifest factory — only for cases the real registry can't express
# ---------------------------------------------------------------------------

def _mk(
    dataset_id,
    *,
    organism="human",
    modality="bulk_microarray",
    data_level="log_expression",
    feature_id_type="gene_symbol",
    requires_collapse=None,
    group_columns=None,
    metadata_columns=None,
    default_contrasts=None,
    cohort_id="",
    variant="",
):
    """Build a minimal valid DatasetManifest with overridable decision fields."""
    feature_mapping = {} if requires_collapse is None else {"requires_collapse": requires_collapse}
    return DatasetManifest(
        dataset_id=dataset_id,
        title=f"synthetic {dataset_id}",
        accession=dataset_id.upper(),
        organism=organism,
        modality=modality,
        platform="synthetic-platform",
        data_level=data_level,
        feature_id_type=feature_id_type,
        expression_source={"type": "local"},
        metadata_source={"type": "manual"},
        group_columns=group_columns or [],
        valid_workflows=["activity_scoring"],
        limitations=["synthetic test fixture"],
        feature_mapping=feature_mapping,
        metadata_columns=metadata_columns or {},
        default_contrasts=default_contrasts or [],
        cohort_id=cohort_id,
        variant=variant,
    )


# ---------------------------------------------------------------------------
# Gate 5 — data_level poolability (D3): early
# ---------------------------------------------------------------------------

def test_equal_raw_counts_is_early():
    """Two datasets at the same poolable level (raw_counts) -> early."""
    plan = get_integration_plan(["paca_au_rnaseq", "tcga_paad"])
    assert plan["mode"] == "early"
    assert plan["poolable_data_level"] == "raw_counts"
    assert plan["shared_feature_space"] == "gene_symbol"
    assert plan["refusal_rules_triggered"] == []


def test_equal_log_expression_is_early():
    """Two gene_symbol microarray datasets at log_expression -> early."""
    plan = get_integration_plan(["gse71729_moffitt", "gse50827_nones"])
    assert plan["mode"] == "early"
    assert plan["poolable_data_level"] == "log_expression"
    assert plan["requires_probe_collapse"] is False
    assert plan["requires_ortholog_mapping"] is False


def test_ensembl_dataset_maps_into_early():
    """ensembl_gene_id id-maps to gene_symbol; equal raw_counts -> early."""
    plan = get_integration_plan(["tcga_paad", "paca_ca_rnaseq"])
    assert plan["mode"] == "early"
    assert plan["shared_feature_space"] == "gene_symbol"
    assert plan["poolable_data_level"] == "raw_counts"
    assert plan["requires_probe_collapse"] is False


def test_probe_collapse_dataset_is_early_with_flag():
    """Worked example: moffitt (gene_symbol) + jiang (probe_id, collapse) -> early."""
    plan = get_integration_plan(["gse71729_moffitt", "gse62165_jiang"])
    assert plan["mode"] == "early"
    assert plan["poolable_data_level"] == "log_expression"
    assert plan["requires_probe_collapse"] is True


# ---------------------------------------------------------------------------
# Gate 5 — data_level poolability (D3): late
# ---------------------------------------------------------------------------

def test_mixed_levels_is_late():
    """log_expression + raw_counts -> late (not a refusal)."""
    plan = get_integration_plan(["gse71729_moffitt", "tcga_paad"])
    assert plan["mode"] == "late"
    assert plan["refusal_rules_triggered"] == []
    assert plan["poolable_data_level"] is None
    assert "mixed data_level" in plan["reason"].lower()


def test_equal_normalized_is_late_not_early():
    """The deliberate exclusion: equal 'normalized' never pools -> late."""
    a = _mk("syn_norm_a", data_level="normalized")
    b = _mk("syn_norm_b", data_level="normalized")
    plan = plan_for_manifests([a, b])
    assert plan["mode"] == "late"
    assert plan["mode"] != "early"
    assert plan["poolable_data_level"] is None
    assert plan["refusal_rules_triggered"] == []
    assert "normalized" in plan["reason"].lower()


def test_equal_protein_abundance_is_late():
    """protein_abundance is never early either; equal level still meta-analyzes."""
    a = _mk("syn_prot_a", modality="proteomics", data_level="protein_abundance",
            feature_id_type="protein_id")
    b = _mk("syn_prot_b", modality="proteomics", data_level="protein_abundance",
            feature_id_type="protein_id")
    plan = plan_for_manifests([a, b])
    assert plan["mode"] == "late"
    assert plan["poolable_data_level"] is None


# ---------------------------------------------------------------------------
# Gate 3 — shared feature space
# ---------------------------------------------------------------------------

def test_probe_without_collapse_refused():
    """probe_id with requires_collapse=False has no gene_symbol mapping -> refuse."""
    a = _mk("syn_probe_nocollapse", feature_id_type="probe_id", requires_collapse=False)
    b = _mk("syn_symbol", feature_id_type="gene_symbol")
    plan = plan_for_manifests([a, b])
    assert plan["mode"] == "refuse"
    assert NO_SHARED_FEATURE_SPACE in plan["refusal_rules_triggered"]
    assert plan["shared_feature_space"] is None


# ---------------------------------------------------------------------------
# Gate 2 — organism / ortholog bridge
# ---------------------------------------------------------------------------

def test_cross_organism_no_bridge_refused():
    """human + mouse where a cohort can't reach gene_symbol -> refuse."""
    human = _mk("syn_human", organism="human", feature_id_type="gene_symbol")
    mouse = _mk("syn_mouse", organism="mouse", feature_id_type="probe_id",
                requires_collapse=False)
    plan = plan_for_manifests([human, mouse])
    assert plan["mode"] == "refuse"
    assert CROSS_ORGANISM_NO_BRIDGE in plan["refusal_rules_triggered"]


def test_bridgeable_cross_organism_continues():
    """human + mouse both in gene_symbol space -> continue with ortholog flag."""
    human = _mk("syn_human2", organism="human", data_level="raw_counts",
                modality="bulk_rnaseq", feature_id_type="gene_symbol")
    mouse = _mk("syn_mouse2", organism="mouse", data_level="raw_counts",
                modality="bulk_rnaseq", feature_id_type="gene_symbol")
    plan = plan_for_manifests([human, mouse])
    assert plan["mode"] != "refuse"
    assert plan["requires_ortholog_mapping"] is True
    assert plan["mode"] == "early"  # equal raw_counts


# ---------------------------------------------------------------------------
# Gate 4 — modality
# ---------------------------------------------------------------------------

def test_cross_modality_refused():
    """transcriptomics + proteomics -> refuse (v1 conservative)."""
    rna = _mk("syn_rna", modality="bulk_microarray", data_level="log_expression",
              feature_id_type="gene_symbol")
    prot = _mk("syn_prot", modality="proteomics", data_level="protein_abundance",
               feature_id_type="protein_id")
    plan = plan_for_manifests([rna, prot])
    assert plan["mode"] == "refuse"
    assert CROSS_MODALITY in plan["refusal_rules_triggered"]


# ---------------------------------------------------------------------------
# Gate 4b — resolution (bulk vs single-cell/spatial)
# ---------------------------------------------------------------------------

def test_bulk_plus_single_cell_refused():
    """bulk_rnaseq + sc_rnaseq at the SAME poolable level (raw_counts) -> refuse.

    Equal raw_counts would early-pool without this gate; resolution must win."""
    bulk = _mk("syn_bulk", modality="bulk_rnaseq", data_level="raw_counts",
               feature_id_type="gene_symbol")
    sc = _mk("syn_sc", modality="sc_rnaseq", data_level="raw_counts",
             feature_id_type="gene_symbol")
    plan = plan_for_manifests([bulk, sc])
    assert plan["mode"] == "refuse"
    assert CROSS_RESOLUTION in plan["refusal_rules_triggered"]


def test_bulk_plus_spatial_refused():
    """spatial_rnaseq counts as single-cell resolution -> refuse against bulk."""
    bulk = _mk("syn_bulk2", modality="bulk_microarray", data_level="log_expression",
               feature_id_type="gene_symbol")
    spatial = _mk("syn_spatial", modality="spatial_rnaseq", data_level="raw_counts",
                  feature_id_type="gene_symbol")
    plan = plan_for_manifests([bulk, spatial])
    assert plan["mode"] == "refuse"
    assert CROSS_RESOLUTION in plan["refusal_rules_triggered"]


def test_two_single_cell_same_resolution_not_cross_resolution():
    """Two sc datasets share resolution -> the resolution gate does not fire
    (they proceed to the data_level gate)."""
    a = _mk("syn_sc_a", modality="sc_rnaseq", data_level="raw_counts",
            feature_id_type="gene_symbol")
    b = _mk("syn_sc_b", modality="sc_rnaseq", data_level="raw_counts",
            feature_id_type="gene_symbol")
    plan = plan_for_manifests([a, b])
    assert CROSS_RESOLUTION not in plan["refusal_rules_triggered"]
    assert plan["mode"] != "refuse"


def test_single_cell_analysis_path_is_p():
    """An sc raw_counts dataset reports analysis_path 'P', not 'A' (no
    DESeq2-on-cells). Surfaced in per_dataset so the agent routes pseudobulk."""
    a = _mk("syn_sc_path", modality="sc_rnaseq", data_level="raw_counts",
            feature_id_type="gene_symbol")
    b = _mk("syn_sc_path_b", modality="sc_rnaseq", data_level="raw_counts",
            feature_id_type="gene_symbol")
    plan = plan_for_manifests([a, b])
    assert all(e["analysis_path"] == "P" for e in plan["per_dataset"])


# ---------------------------------------------------------------------------
# Gate 1 — arity
# ---------------------------------------------------------------------------

def test_single_dataset_refused_not_multi():
    """A single dataset cannot be integrated -> refuse / NOT_MULTI."""
    plan = get_integration_plan(["tcga_paad"])
    assert plan["mode"] == "refuse"
    assert NOT_MULTI in plan["refusal_rules_triggered"]
    assert len(plan["per_dataset"]) == 1


def test_empty_list_refused_not_multi():
    """Zero datasets -> refuse / NOT_MULTI with empty per_dataset."""
    plan = get_integration_plan([])
    assert plan["mode"] == "refuse"
    assert NOT_MULTI in plan["refusal_rules_triggered"]
    assert plan["per_dataset"] == []


# ---------------------------------------------------------------------------
# Gate 1b — same-cohort variants (sibling quantifications of one cohort)
# ---------------------------------------------------------------------------

def test_sibling_pair_is_concordance():
    """Two datasets sharing a cohort_id -> concordance, NOT late/early.

    Uses different data_levels (tpm vs normalized) to prove the cohort gate
    pre-empts the data_level gate that would otherwise route this to 'late'.
    """
    a = _mk("c1_tpm", data_level="tpm", cohort_id="c1", variant="tpm")
    b = _mk("c1_tmm", data_level="normalized", cohort_id="c1", variant="tmm")
    plan = plan_for_manifests([a, b])
    assert plan["mode"] == CONCORDANCE
    assert plan["mode"] not in ("late", "early")
    assert plan["refusal_rules_triggered"] == []
    assert "concordance" in plan["reason"].lower()
    # per_dataset carries the cohort grouping the agent acts on
    assert all(e["cohort_id"] == "c1" for e in plan["per_dataset"])
    assert {e["variant"] for e in plan["per_dataset"]} == {"tpm", "tmm"}


def test_sibling_concordance_has_full_contract():
    """A concordance plan still carries the full top-level key set."""
    a = _mk("c2_a", cohort_id="c2", variant="tpm")
    b = _mk("c2_b", cohort_id="c2", variant="tmm")
    plan = plan_for_manifests([a, b])
    assert set(plan.keys()) == PLAN_KEYS
    assert plan["mode"] == CONCORDANCE


def test_full_sibling_trio_is_concordance_real():
    """The real GSE205154 trio (TPM/counts/TMM) -> concordance.

    These are the same 289 samples; counts is Path A and the others Path B, so
    pre-cohort-gate this mixed-level set would have meta-analyzed ('late')."""
    plan = get_integration_plan(
        ["gse205154_sears", "gse205154_sears_counts", "gse205154_sears_tmm"]
    )
    assert plan["mode"] == CONCORDANCE
    assert plan["refusal_rules_triggered"] == []
    assert all(e["cohort_id"] == "gse205154" for e in plan["per_dataset"])


def test_two_real_siblings_is_concordance():
    """The exact case from the agent run: TPM + TMM of one cohort -> concordance
    (not meta-analysis)."""
    plan = get_integration_plan(["gse205154_sears", "gse205154_sears_tmm"])
    assert plan["mode"] == CONCORDANCE


def test_siblings_mixed_with_independent_dataset_refused():
    """Sibling variants requested alongside an independent dataset -> refuse
    DUPLICATE_COHORT: they can't be independent inputs to a meta-analysis."""
    plan = get_integration_plan(
        ["gse205154_sears", "gse205154_sears_tmm", "tcga_paad"]
    )
    assert plan["mode"] == "refuse"
    assert DUPLICATE_COHORT in plan["refusal_rules_triggered"]


def test_two_distinct_duplicated_cohorts_refused():
    """Two siblings of cohort A + two of cohort B (no clean integration) ->
    refuse DUPLICATE_COHORT."""
    a1 = _mk("a_tpm", cohort_id="A", data_level="tpm", variant="tpm")
    a2 = _mk("a_tmm", cohort_id="A", data_level="normalized", variant="tmm")
    b1 = _mk("b_tpm", cohort_id="B", data_level="tpm", variant="tpm")
    b2 = _mk("b_tmm", cohort_id="B", data_level="normalized", variant="tmm")
    plan = plan_for_manifests([a1, a2, b1, b2])
    assert plan["mode"] == "refuse"
    assert DUPLICATE_COHORT in plan["refusal_rules_triggered"]


def test_distinct_single_cohort_ids_not_concordance():
    """Datasets with DIFFERENT cohort_ids (each appearing once) are independent —
    the gate only fires on a SHARED cohort_id. Equal raw_counts -> early."""
    p = _mk("p_only", cohort_id="P", data_level="raw_counts",
            modality="bulk_rnaseq", feature_id_type="gene_symbol")
    q = _mk("q_only", cohort_id="Q", data_level="raw_counts",
            modality="bulk_rnaseq", feature_id_type="gene_symbol")
    plan = plan_for_manifests([p, q])
    assert plan["mode"] != CONCORDANCE
    assert plan["mode"] == "early"


def test_no_cohort_id_is_unaffected():
    """Datasets without a cohort_id behave exactly as before (regression):
    mixed levels -> late, never concordance."""
    a = _mk("plain_tpm", data_level="tpm")
    b = _mk("plain_norm", data_level="normalized")
    plan = plan_for_manifests([a, b])
    assert plan["mode"] == "late"
    assert plan["mode"] != CONCORDANCE


# ---------------------------------------------------------------------------
# Gate 6 — confound (metadata-level only, requires a requested contrast)
# ---------------------------------------------------------------------------

def _single_arm(value):
    return {"condition": MetadataColumnDef(role="primary_condition", allowed_values=[value])}


def test_confounded_design_refused():
    """All-tumor cohort + all-normal cohort, contrast tumor vs normal -> refuse."""
    a = _mk("syn_tumor_only", group_columns=["condition"],
            metadata_columns=_single_arm("tumor"))
    b = _mk("syn_normal_only", group_columns=["condition"],
            metadata_columns=_single_arm("normal"))
    plan = plan_for_manifests(
        [a, b], design_factor="condition", test_group="tumor", control_group="normal"
    )
    assert plan["mode"] == "refuse"
    assert CONFOUNDED_DESIGN in plan["refusal_rules_triggered"]


def test_non_separable_contrast_not_refused():
    """When a cohort declares both arms, the design is not separable -> not refused."""
    both = {"condition": MetadataColumnDef(role="primary_condition",
                                           allowed_values=["tumor", "normal"])}
    a = _mk("syn_both_a", group_columns=["condition"], metadata_columns=both)
    b = _mk("syn_both_b", group_columns=["condition"], metadata_columns=both)
    plan = plan_for_manifests(
        [a, b], design_factor="condition", test_group="tumor", control_group="normal"
    )
    assert plan["mode"] != "refuse"
    assert CONFOUNDED_DESIGN not in plan["refusal_rules_triggered"]


def test_confound_deferred_without_contrast():
    """No requested contrast -> Gate 6 defers, never fabricates CONFOUNDED_DESIGN."""
    a = _mk("syn_tumor_only2", group_columns=["condition"],
            metadata_columns=_single_arm("tumor"))
    b = _mk("syn_normal_only2", group_columns=["condition"],
            metadata_columns=_single_arm("normal"))
    plan = plan_for_manifests([a, b])  # no design_factor
    assert plan["mode"] != "refuse"
    assert CONFOUNDED_DESIGN not in plan["refusal_rules_triggered"]


def test_confound_deferred_when_arms_unspecified():
    """Factor declared but no arms in metadata -> defer (specialist's job)."""
    a = _mk("syn_unspec_a", group_columns=["condition"])  # no allowed_values
    b = _mk("syn_unspec_b", group_columns=["condition"])
    plan = plan_for_manifests(
        [a, b], design_factor="condition", test_group="tumor", control_group="normal"
    )
    assert plan["mode"] != "refuse"


def test_factor_absent_in_one_cohort_refused():
    """A contrast whose factor is absent from one cohort is confounded with
    dataset -> refuse. The cohort that lacks the factor cannot contribute either
    arm, so the contrast lives in only the other dataset (a single cohort
    relabelled). Even though the labelled cohort declares both arms, combining is
    invalid (this is the case the old 'no cohort declares both arms' rule missed).
    """
    labelled = _mk(
        "syn_subtyped",
        group_columns=["subtype"],
        metadata_columns={"subtype": MetadataColumnDef(
            role="primary_condition",
            allowed_values=["Squamous", "Pancreatic Progenitor"])},
    )
    unlabelled = _mk("syn_no_subtype", group_columns=["stage"])  # no 'subtype'
    plan = plan_for_manifests(
        [labelled, unlabelled],
        design_factor="subtype",
        test_group="Squamous", control_group="Pancreatic Progenitor",
    )
    assert plan["mode"] == "refuse"
    assert CONFOUNDED_DESIGN in plan["refusal_rules_triggered"]


def test_cohort_with_disjoint_arms_refused():
    """A cohort that declares the factor but none of the requested arms cannot
    contribute to the contrast -> refuse (neither requested arm is available)."""
    wanted_cohort = _mk(
        "syn_has_arms",
        group_columns=["subtype"],
        metadata_columns={"subtype": MetadataColumnDef(
            role="primary_condition",
            allowed_values=["Squamous", "Pancreatic Progenitor"])},
    )
    disjoint_cohort = _mk(
        "syn_other_arms",
        group_columns=["subtype"],
        metadata_columns={"subtype": MetadataColumnDef(
            role="primary_condition",
            allowed_values=["Classical", "Basal"])},  # disjoint from requested pair
    )
    plan = plan_for_manifests(
        [wanted_cohort, disjoint_cohort],
        design_factor="subtype",
        test_group="Squamous", control_group="Pancreatic Progenitor",
    )
    assert plan["mode"] == "refuse"
    assert CONFOUNDED_DESIGN in plan["refusal_rules_triggered"]


def test_bailey_contrast_across_unlabelled_cohort_refused():
    """Real registered datasets (ADR-0001 Case 3): a Bailey-subtype contrast
    across paca_au_rnaseq (has membership.ordered) + tcga_paad (does not) is
    confounded with dataset -> refuse. Without this, the agent would silently
    produce a paca_au-only result presented as cross-dataset."""
    plan = get_integration_plan(
        ["paca_au_rnaseq", "tcga_paad"],
        design_factor="membership.ordered",
        test_group="Squamous", control_group="Pancreatic Progenitor",
    )
    assert plan["mode"] == "refuse"
    assert CONFOUNDED_DESIGN in plan["refusal_rules_triggered"]


def test_partial_imbalance_not_refused():
    """One cohort has both arms, the other supplies only one (skewed but
    contributing) -> NOT a refusal: the early-mode batch covariate handles it."""
    both = _mk(
        "syn_full",
        group_columns=["condition"],
        metadata_columns={"condition": MetadataColumnDef(
            role="primary_condition", allowed_values=["tumor", "normal"])},
    )
    one_arm = _mk(
        "syn_skew",
        group_columns=["condition"],
        metadata_columns=_single_arm("tumor"),  # contributes the 'tumor' arm only
    )
    plan = plan_for_manifests(
        [both, one_arm],
        design_factor="condition", test_group="tumor", control_group="normal",
    )
    assert plan["mode"] != "refuse"
    assert CONFOUNDED_DESIGN not in plan["refusal_rules_triggered"]


# ---------------------------------------------------------------------------
# Output contract
# ---------------------------------------------------------------------------

def test_every_plan_has_nonempty_reason():
    """Every verdict — early, late, and each refusal — carries a non-empty reason."""
    plans = [
        get_integration_plan(["paca_au_rnaseq", "tcga_paad"]),          # early
        get_integration_plan(["gse71729_moffitt", "tcga_paad"]),        # late
        get_integration_plan(["gse205154_sears", "gse205154_sears_tmm"]),  # concordance
        get_integration_plan(["tcga_paad"]),                            # NOT_MULTI
        plan_for_manifests([                                            # NO_SHARED...
            _mk("p1", feature_id_type="probe_id", requires_collapse=False),
            _mk("p2", feature_id_type="gene_symbol"),
        ]),
        plan_for_manifests([                                            # CROSS_ORGANISM
            _mk("h", organism="human"),
            _mk("m", organism="mouse", feature_id_type="probe_id", requires_collapse=False),
        ]),
        plan_for_manifests([                                            # CROSS_MODALITY
            _mk("r", modality="bulk_rnaseq", data_level="raw_counts"),
            _mk("pr", modality="proteomics", data_level="protein_abundance",
                feature_id_type="protein_id"),
        ]),
        plan_for_manifests(                                            # CONFOUNDED
            [_mk("t", group_columns=["condition"], metadata_columns=_single_arm("tumor")),
             _mk("n", group_columns=["condition"], metadata_columns=_single_arm("normal"))],
            design_factor="condition", test_group="tumor", control_group="normal",
        ),
    ]
    for plan in plans:
        assert isinstance(plan["reason"], str)
        assert plan["reason"].strip(), f"empty reason for plan: {plan['mode']}"


def test_plan_has_all_top_level_keys():
    """The plan dict always carries the full set of documented keys."""
    plan = get_integration_plan(["paca_au_rnaseq", "tcga_paad"])
    assert set(plan.keys()) == PLAN_KEYS
    assert plan["batch_key"] == "dataset_id"


def test_per_dataset_entry_shape():
    """Each per_dataset entry exposes the documented fields."""
    plan = get_integration_plan(["paca_au_rnaseq", "tcga_paad"])
    assert len(plan["per_dataset"]) == 2
    for entry in plan["per_dataset"]:
        assert set(entry.keys()) == PER_DATASET_KEYS


def test_unknown_dataset_raises_value_error():
    """An unregistered dataset_id raises ValueError listing available datasets."""
    with pytest.raises(ValueError, match="not found in registry"):
        get_integration_plan(["tcga_paad", "nonexistent_dataset_xyz"])


# ---------------------------------------------------------------------------
# MCP tool wiring (skipped when fastmcp is not installed)
# ---------------------------------------------------------------------------

def test_mcp_server_exposes_integration_tool():
    """server.py imports cleanly with the 5th tool registered (needs fastmcp)."""
    pytest.importorskip("fastmcp")
    from biodata_registry import server
    assert hasattr(server, "get_integration_plan")
    assert hasattr(server, "mcp")
