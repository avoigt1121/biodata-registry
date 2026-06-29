"""
Cross-dataset compatibility engine (ADR-0001 Phase 1, step 2).

``get_integration_plan`` decides whether a set of datasets can be combined

  * **early** — pool the expression matrices and fit one model with
    ``dataset_id`` as a batch covariate, or
  * **late** — analyze each dataset separately and meta-analyze the results, or
  * **concordance** — the requested datasets are *sibling variants of one
    cohort* (same samples, different quantification/units; they share a
    ``cohort_id``). They must NOT be integrated or meta-analyzed — that
    double-counts the cohort. Run each variant separately and compare with
    descriptive agreement metrics (a normalization sensitivity check), or
  * **refuse** — the datasets are incompatible for any route (including
    ``DUPLICATE_COHORT``: sibling variants requested alongside independent
    datasets — pick one variant per cohort first).

The decision is a **pure function of manifest metadata** — no data is loaded.
This deliberately keeps the registry metadata-pure: the *sample-level* confound
check (are both contrast arms actually populated in each cohort after
subsetting?) and the actual pooling / correction / meta-analysis happen later in
the specialist. See docs/adr/ADR-0001-decision-matrix.md ("Registry vs specialist").

Resolution order (first failing gate decides; short-circuit on ``refuse``)
--------------------------------------------------------------------------
1.  arity        < 2 datasets                 -> refuse  (NOT_MULTI)
1b. cohort       >=2 requested datasets share a ``cohort_id`` (same samples,
                 different quantification):
                 all requested are one cohort -> concordance
                 siblings + other datasets    -> refuse  (DUPLICATE_COHORT)
2.  organism     mixed & no ortholog bridge   -> refuse  (CROSS_ORGANISM_NO_BRIDGE)
                 mixed & bridgeable           -> requires_ortholog_mapping=True, continue
3.  feature      no shared gene_symbol space  -> refuse  (NO_SHARED_FEATURE_SPACE)
4.  modality     transcriptome + proteome     -> refuse  (CROSS_MODALITY)   [v1]
4b. resolution   bulk + single-cell/spatial   -> refuse  (CROSS_RESOLUTION)  [v1]
5.  data_level   poolable & EQUAL on all       -> early-eligible; else -> late   (D3)
6.  confound     a requested contrast is confounded with dataset:
                 a cohort supplies neither arm, or no cohort
                 supplies both arms           -> refuse  (CONFOUNDED_DESIGN)
                 else early-eligible -> early; else -> late

Gate 1b runs before the data_level gate on purpose. Sibling variants differ
*only* in quantification, so without it a TPM+TMM request (``tpm`` !=
``normalized``) would fall through Gate 5 to ``late`` and be meta-analyzed —
exactly the double-counting we must prevent. ``concordance`` is not a refusal;
it carries an empty ``refusal_rules_triggered``.

``early`` -> ``late`` downgrades are **not** refusals — they carry a clear
``reason`` and an empty ``refusal_rules_triggered``.

Gate 4b (resolution) mirrors the proteome pattern: bulk (sample × gene) and
single-cell/spatial (cell/spot × gene) data live at different units of
observation. Pooling them as one matrix is meaningless, and a bulk+sc request
otherwise slips through the modality gate (both are "transcriptome") into the
data_level gate, which would early-pool equal raw_counts. The valid routes are
deconvolution, signature transfer, or pseudobulk-then-meta-analyze — none of
which this metadata-pure engine performs — so v1 refuses, exactly as Gate 4 does
for transcriptome+proteome. This may graduate to a dedicated mode later (as
``concordance`` did).

Gate 5 (D3, signed off) is the key rule: early integration requires the *same*
``data_level`` on every dataset, and that level must be in the poolable set.
``normalized`` (scale unspecified) and ``protein_abundance`` are deliberately
never poolable — even when equal across datasets they meta-analyze.

Gate 6 only fires when the caller supplies the contrast it intends to run via
the optional ``design_factor`` / ``test_group`` / ``control_group`` arguments.
Without a requested contrast the registry cannot tell which design is at stake,
so design separability is deferred to the specialist (and this function never
fabricates a CONFOUNDED_DESIGN refusal).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .manifest_schema import DatasetManifest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Obs column used as the batch covariate when pooling early.
BATCH_KEY = "dataset_id"

#: Common feature space decoupleR networks are keyed on.
TARGET_FEATURE_SPACE = "gene_symbol"

#: Modality treated as the proteome side of the transcriptome/proteome split.
PROTEOMICS_MODALITY = "proteomics"

#: Modalities whose unit of observation is a cell/spot rather than a sample.
#: A request mixing these with bulk modalities is refused (CROSS_RESOLUTION):
#: the matrices are not poolable across resolutions.
SINGLE_CELL_MODALITIES = frozenset({"sc_rnaseq", "spatial_rnaseq"})

#: data_levels that may be pooled *early* — but only when EQUAL across all
#: datasets (Gate 5 / D3). raw_counts is the sole Path-A level; the rest are
#: Path-B scales that are only comparable enough to batch-correct when identical.
POOLABLE_EARLY_LEVELS = frozenset({
    "raw_counts",      # Path A — DESeq2 ~ batch + condition
    "log_expression",  # Path B — limma, batch in design
    "log_ratio",       # Path B — limma, batch in design (two-color arrays)
    "tpm",             # Path B — log2(tpm+1) -> limma + batch
    "fpkm",            # Path B — log2(fpkm+1) -> limma + batch
})

#: data_levels that are *never* eligible for early pooling, even when equal:
#: 'normalized' has an unspecified scale; 'protein_abundance' is proteomics.
NEVER_EARLY_LEVELS = frozenset({"normalized", "protein_abundance"})

# Stable refusal codes surfaced in refusal_rules_triggered.
NOT_MULTI = "NOT_MULTI"
DUPLICATE_COHORT = "DUPLICATE_COHORT"
CROSS_ORGANISM_NO_BRIDGE = "CROSS_ORGANISM_NO_BRIDGE"
NO_SHARED_FEATURE_SPACE = "NO_SHARED_FEATURE_SPACE"
CROSS_MODALITY = "CROSS_MODALITY"
CROSS_RESOLUTION = "CROSS_RESOLUTION"
CONFOUNDED_DESIGN = "CONFOUNDED_DESIGN"

#: Non-refusal mode for sibling variants of a single cohort — compare, don't combine.
CONCORDANCE = "concordance"


# ---------------------------------------------------------------------------
# Per-dataset helpers (pure)
# ---------------------------------------------------------------------------

def _per_dataset_entry(m: "DatasetManifest") -> dict:
    """Compact metadata summary for one dataset in the plan output."""
    return {
        "dataset_id": m.dataset_id,
        "organism": m.organism,
        "modality": m.modality,
        "data_level": m.data_level,
        "analysis_path": m.analysis_path,
        "feature_id_type": m.feature_id_type,
        "requires_collapse": bool(m.feature_mapping.get("requires_collapse", False)),
        "cohort_id": getattr(m, "cohort_id", "") or "",
        "variant": getattr(m, "variant", "") or "",
    }


def _reaches_gene_symbol(m: "DatasetManifest") -> tuple[bool, bool]:
    """
    Can this dataset be expressed in the common ``gene_symbol`` space?

    Returns ``(reachable, via_probe_collapse)``:

    - ``gene_symbol``                       -> (True, False)  direct
    - ``ensembl_gene_id`` / ``entrez_id``   -> (True, False)  id-map to symbol
    - ``probe_id`` + requires_collapse=True -> (True, True)   collapse first
    - ``probe_id`` + requires_collapse!=True -> (False, False) no usable mapping
    - ``protein_id``                        -> (True, False)  protein->gene map;
      the transcriptome/proteome split is the modality gate's job (Gate 4), not
      this one, so protein_id does not by itself fail the feature gate.
    """
    ft = m.feature_id_type
    if ft == TARGET_FEATURE_SPACE:
        return True, False
    if ft in ("ensembl_gene_id", "entrez_id"):
        return True, False
    if ft == "probe_id":
        if bool(m.feature_mapping.get("requires_collapse")):
            return True, True
        return False, False
    if ft == "protein_id":
        return True, False
    return False, False


def _declarable_arms(m: "DatasetManifest", factor: str) -> set[str]:
    """
    Biological arm labels this cohort can express for ``factor``, from metadata.

    Drawn from ``metadata_columns[factor].allowed_values`` (minus that column's
    declared missing markers) and from any ``default_contrasts`` whose
    ``design_factor`` is ``factor``. Empty set => no arms knowable from metadata.
    """
    arms: set[str] = set()
    col = m.metadata_columns.get(factor)
    if col is not None:
        missing = set(getattr(col, "missing_values", []) or [])
        for v in (getattr(col, "allowed_values", []) or []):
            if str(v).strip() and v not in missing:
                arms.add(v)
    for c in m.default_contrasts:
        if c.get("design_factor") == factor:
            for key in ("test_group", "control_group"):
                v = c.get(key)
                if v is not None and str(v).strip():
                    arms.add(v)
    return arms


def _declares_factor(m: "DatasetManifest", factor: str) -> bool:
    """True if the cohort references ``factor`` anywhere in its metadata."""
    return (
        factor in m.group_columns
        or m.metadata_columns.get(factor) is not None
        or any(c.get("design_factor") == factor for c in m.default_contrasts)
    )


def _confound_separates(
    manifests: list["DatasetManifest"],
    design_factor: str,
    test_group: Optional[str],
    control_group: Optional[str],
) -> tuple[bool, str]:
    """
    Does manifest metadata *positively* show the requested contrast cannot be run
    as a valid cross-dataset comparison (confounded with dataset)?

    Two distinct ways a contrast is confounded with dataset, both refused here:

    1. **A cohort contributes neither arm.** If a requested cohort cannot supply
       *either* arm of the contrast from its metadata — the design factor is
       absent entirely, or its declared arms are disjoint from the requested
       pair — then the contrast lives in only a subset of the requested datasets.
       Combining cannot produce a cross-dataset comparison for it (the "combined"
       result would be a single cohort relabelled), so refuse. This is the Case-3
       guard: e.g. a Bailey-subtype contrast across a Bailey-labelled cohort +
       one with no Bailey labels.
    2. **No single cohort declares both arms** (perfectly split design): each
       cohort supplies only one arm, so arm is perfectly aliased with dataset.

    Conservative on purpose. Partial imbalance (one cohort has both arms, another
    is skewed but still contributes an arm) is *not* separation — that is exactly
    what the early-mode batch covariate handles. A cohort that declares the factor
    but lists no arms (allowed_values/contrasts absent) is *unknown*, not absent:
    we cannot prove confounding from metadata, so we defer to the specialist's
    runtime check rather than refuse.

    Returns ``(separable, detail)`` where ``detail`` summarises per-cohort arms.
    """
    wanted: Optional[set[str]] = None
    if test_group is not None and control_group is not None:
        wanted = {test_group, control_group}

    summary: dict[str, object] = {}
    can_run_full: list[Optional[bool]] = []  # supplies BOTH arms (runs contrast alone)
    contributes: list[Optional[bool]] = []   # supplies >=1 arm (True/False) or unknown
    for m in manifests:
        arms = _declarable_arms(m, design_factor)
        if not arms:
            if _declares_factor(m, design_factor):
                summary[m.dataset_id] = "<arms unspecified>"
                can_run_full.append(None)        # present but unknowable -> defer
                contributes.append(None)
            else:
                summary[m.dataset_id] = "<factor absent>"
                can_run_full.append(False)       # cannot supply either arm
                contributes.append(False)
            continue
        summary[m.dataset_id] = sorted(arms)
        if wanted is not None:
            can_run_full.append(wanted.issubset(arms))
            contributes.append(bool(wanted & arms))   # >=1 of the requested arms
        else:
            can_run_full.append(len(arms) >= 2)       # factor only -> need >=2 arms
            contributes.append(len(arms) >= 1)

    detail = ", ".join(f"{k}={v}" for k, v in summary.items())

    # (1) A cohort that definitively contributes neither arm cannot take part in
    #     a cross-dataset comparison for this contrast -> confounded with dataset.
    #     A definite absence is decisive even if another cohort is unknown.
    if any(c is False for c in contributes):
        return True, detail
    # (2) If a cohort can run the full contrast alone, the design is not separable
    #     across datasets (partial imbalance is the batch covariate's job).
    if any(s is True for s in can_run_full):
        return False, ""
    # Insufficient metadata anywhere -> defer to the specialist's runtime check.
    if any(s is None for s in can_run_full):
        return False, ""
    # Every cohort supplies exactly one (different) arm -> perfectly split.
    return True, detail


# ---------------------------------------------------------------------------
# Result construction
# ---------------------------------------------------------------------------

def _build(
    *,
    mode: str,
    reason: str,
    per_dataset: list[dict],
    shared_feature_space: Optional[str] = None,
    requires_ortholog_mapping: bool = False,
    requires_probe_collapse: bool = False,
    poolable_data_level: Optional[str] = None,
    refusal_rules_triggered: Optional[list[str]] = None,
) -> dict:
    """Assemble the plan dict with stable key order and defaults."""
    return {
        "mode": mode,
        "reason": reason,
        "shared_feature_space": shared_feature_space,
        "requires_ortholog_mapping": requires_ortholog_mapping,
        "requires_probe_collapse": requires_probe_collapse,
        "batch_key": BATCH_KEY,
        "poolable_data_level": poolable_data_level,
        "per_dataset": per_dataset,
        "refusal_rules_triggered": list(refusal_rules_triggered or []),
    }


def _late_reason(levels: set[str]) -> str:
    """Human-readable reason for a late (meta-analysis) verdict."""
    if len(levels) > 1:
        return (
            f"Mixed data_level across datasets ({sorted(levels)}) — pooling raw "
            f"values across different quantification scales is invalid; "
            f"meta-analyzing per-dataset results instead."
        )
    lvl = next(iter(levels))
    if lvl == "normalized":
        return (
            "All datasets share data_level 'normalized', but its scale is "
            "unspecified — values are not guaranteed comparable across cohorts, "
            "so they are never pooled; meta-analyzing per-dataset results instead."
        )
    if lvl == "protein_abundance":
        return (
            "All datasets share data_level 'protein_abundance' (proteomics) — "
            "abundances are not pooled across cohorts in v1; meta-analyzing "
            "per-dataset results instead."
        )
    # Defensive: a single poolable level resolves to early, so this is unexpected.
    return (
        f"All datasets share data_level '{lvl}', which is not eligible for early "
        f"pooling; meta-analyzing per-dataset results instead."
    )


def _group_by_cohort(manifests: list["DatasetManifest"]) -> dict[str, list[str]]:
    """Map ``cohort_id`` -> ``[dataset_id]`` for manifests that declare a
    non-empty ``cohort_id`` (sibling quantifications of one cohort)."""
    groups: dict[str, list[str]] = {}
    for m in manifests:
        cid = (getattr(m, "cohort_id", "") or "").strip()
        if cid:
            groups.setdefault(cid, []).append(m.dataset_id)
    return groups


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def plan_for_manifests(
    manifests: list["DatasetManifest"],
    design_factor: Optional[str] = None,
    test_group: Optional[str] = None,
    control_group: Optional[str] = None,
) -> dict:
    """
    Decide the integration plan for already-loaded manifests (pure logic).

    This is the engine behind :func:`get_integration_plan`, exposed separately
    so it can be unit-tested against constructed :class:`DatasetManifest`
    objects without touching the registry. See the module docstring for the
    gate order and the meaning of each output key.
    """
    per_dataset = [_per_dataset_entry(m) for m in manifests]

    # Gate 1 — arity
    if len(manifests) < 2:
        ids = [m.dataset_id for m in manifests] or "none"
        return _build(
            mode="refuse",
            reason=(
                f"Integration needs at least 2 datasets; received "
                f"{len(manifests)} ({ids})."
            ),
            per_dataset=per_dataset,
            refusal_rules_triggered=[NOT_MULTI],
        )

    # Gate 1b — same-cohort variants (sibling quantifications of one cohort)
    # Runs before the data_level gate: siblings differ only in quantification, so
    # a TPM+TMM request would otherwise fall through to 'late' and be
    # meta-analyzed — double-counting the identical samples.
    duplicated = {
        cid: ids for cid, ids in _group_by_cohort(manifests).items() if len(ids) >= 2
    }
    if duplicated:
        total_in_dups = sum(len(ids) for ids in duplicated.values())
        all_one_cohort = len(duplicated) == 1 and total_in_dups == len(manifests)
        if all_one_cohort:
            cid = next(iter(duplicated))
            variants = ", ".join(
                f"{m.dataset_id} ({m.variant or m.data_level})" for m in manifests
            )
            return _build(
                mode=CONCORDANCE,
                reason=(
                    f"All {len(manifests)} requested datasets are sibling "
                    f"quantifications of one cohort '{cid}' ({variants}). They are "
                    f"the same samples in different units, so they must NOT be "
                    f"pooled or meta-analyzed: combining identical samples "
                    f"double-counts the cohort (Stouffer inflates the combined "
                    f"score by ~sqrt(N); Cochran's Q / I^2 collapse to 0 by "
                    f"construction, so zero heterogeneity is guaranteed, not "
                    f"evidence of robustness). Run the analysis on each variant "
                    f"separately and compare them with descriptive agreement "
                    f"metrics (Pearson/Spearman on scores, sign-concordance, "
                    f"overlap of significant calls) — a normalization concordance "
                    f"/ sensitivity check, not an integration."
                ),
                per_dataset=per_dataset,
                refusal_rules_triggered=[],
            )
        dup_desc = "; ".join(f"{cid}: {sorted(ids)}" for cid, ids in duplicated.items())
        return _build(
            mode="refuse",
            reason=(
                f"The request mixes >=2 quantifications of the same cohort "
                f"({dup_desc}) with other datasets. Sibling variants are the same "
                f"samples in different units and cannot be independent inputs to "
                f"an integration or meta-analysis (that double-counts the cohort). "
                f"Pick exactly one variant per cohort, then re-request. To compare "
                f"a single cohort's quantifications, request only that cohort's "
                f"variants (yields mode='concordance')."
            ),
            per_dataset=per_dataset,
            refusal_rules_triggered=[DUPLICATE_COHORT],
        )

    # Gate 2 — organism (cross-species ortholog bridge)
    organisms = {m.organism for m in manifests}
    requires_ortholog_mapping = False
    if len(organisms) > 1:
        # Orthology bridges symbol<->symbol, so a cross-species mix is only
        # bridgeable if every cohort can reach the gene_symbol space.
        unreachable = [m.dataset_id for m in manifests if not _reaches_gene_symbol(m)[0]]
        if unreachable:
            return _build(
                mode="refuse",
                reason=(
                    f"Datasets span multiple organisms ({sorted(organisms)}) and "
                    f"{unreachable} cannot be mapped into a shared gene_symbol "
                    f"space, so orthology cannot bridge them. Refusing "
                    f"cross-species pooling."
                ),
                per_dataset=per_dataset,
                refusal_rules_triggered=[CROSS_ORGANISM_NO_BRIDGE],
            )
        requires_ortholog_mapping = True

    # Gate 3 — shared feature space (target: gene_symbol)
    reach = {m.dataset_id: _reaches_gene_symbol(m) for m in manifests}
    unreachable = [did for did, (ok, _) in reach.items() if not ok]
    if unreachable:
        return _build(
            mode="refuse",
            reason=(
                f"No shared gene_symbol feature space: {unreachable} cannot be "
                f"mapped to gene symbols (e.g. probe_id without a collapse "
                f"mapping, or proteins without a gene map). Refusing."
            ),
            per_dataset=per_dataset,
            requires_ortholog_mapping=requires_ortholog_mapping,
            refusal_rules_triggered=[NO_SHARED_FEATURE_SPACE],
        )
    requires_probe_collapse = any(via for (_, via) in reach.values())
    shared_feature_space = TARGET_FEATURE_SPACE

    # Gate 4 — modality (v1: no transcriptome/proteome pooling)
    modalities = {m.modality for m in manifests}
    has_proteome = PROTEOMICS_MODALITY in modalities
    has_transcriptome = any(mod != PROTEOMICS_MODALITY for mod in modalities)
    if has_proteome and has_transcriptome:
        return _build(
            mode="refuse",
            reason=(
                f"Cross-modality integration (transcriptomics + proteomics) is "
                f"not supported in v1 (modalities: {sorted(modalities)}). "
                f"Refusing early pooling; a shared meta-analysis envelope across "
                f"modalities is future work."
            ),
            per_dataset=per_dataset,
            shared_feature_space=shared_feature_space,
            requires_ortholog_mapping=requires_ortholog_mapping,
            requires_probe_collapse=requires_probe_collapse,
            refusal_rules_triggered=[CROSS_MODALITY],
        )

    # Gate 4b — resolution (v1: no bulk + single-cell/spatial pooling)
    # Runs before the data_level gate: bulk and sc/spatial can share a poolable
    # data_level (e.g. raw_counts), so without this an sc + bulk request would
    # early-pool cells×genes with samples×genes. Mirrors the proteome gate.
    has_single_cell = any(m.modality in SINGLE_CELL_MODALITIES for m in manifests)
    has_bulk = any(m.modality not in SINGLE_CELL_MODALITIES for m in manifests)
    if has_single_cell and has_bulk:
        return _build(
            mode="refuse",
            reason=(
                f"Cross-resolution integration (bulk + single-cell/spatial) is "
                f"not supported in v1 (modalities: {sorted(modalities)}). Bulk data "
                f"is sample × gene and single-cell/spatial is cell/spot × gene — "
                f"they cannot be pooled into one matrix. Valid routes are "
                f"deconvolution, signature transfer, or pseudobulk-then-"
                f"meta-analyze, none performed by this metadata-only engine. "
                f"Refusing."
            ),
            per_dataset=per_dataset,
            shared_feature_space=shared_feature_space,
            requires_ortholog_mapping=requires_ortholog_mapping,
            requires_probe_collapse=requires_probe_collapse,
            refusal_rules_triggered=[CROSS_RESOLUTION],
        )

    # Gate 5 — data_level poolability (D3, signed off)
    levels = {m.data_level for m in manifests}
    shared_level = next(iter(levels)) if len(levels) == 1 else None
    early_eligible = shared_level is not None and shared_level in POOLABLE_EARLY_LEVELS

    # Gate 6 — confound (only when a contrast is supplied)
    if design_factor is not None:
        separable, detail = _confound_separates(
            manifests, design_factor, test_group, control_group
        )
        if separable:
            contrast_desc = f"'{design_factor}'"
            if test_group is not None and control_group is not None:
                contrast_desc += f" ({test_group} vs {control_group})"
            return _build(
                mode="refuse",
                reason=(
                    f"The requested contrast {contrast_desc} is confounded with "
                    f"dataset: it cannot be run as a valid cross-dataset "
                    f"comparison because at least one cohort cannot supply both "
                    f"arms from its metadata ({detail}). The contrast would be "
                    f"aliased with batch. Refusing."
                ),
                per_dataset=per_dataset,
                shared_feature_space=shared_feature_space,
                requires_ortholog_mapping=requires_ortholog_mapping,
                requires_probe_collapse=requires_probe_collapse,
                refusal_rules_triggered=[CONFOUNDED_DESIGN],
            )

    # Final verdict — early vs late
    if early_eligible:
        reason = (
            f"All {len(manifests)} datasets share data_level '{shared_level}' "
            f"(poolable) and map to a common {shared_feature_space} space — "
            f"pool expression with '{BATCH_KEY}' as the batch covariate."
        )
        if requires_probe_collapse:
            reason += " Probe-level datasets are collapsed to gene symbols first."
        if requires_ortholog_mapping:
            reason += (
                " Cross-species features are ortholog-mapped to a common symbol "
                "space first."
            )
        return _build(
            mode="early",
            reason=reason,
            per_dataset=per_dataset,
            shared_feature_space=shared_feature_space,
            requires_ortholog_mapping=requires_ortholog_mapping,
            requires_probe_collapse=requires_probe_collapse,
            poolable_data_level=shared_level,
        )

    reason = _late_reason(levels)
    if requires_probe_collapse:
        reason += " (Per-dataset probe collapse to gene symbols still applies.)"
    return _build(
        mode="late",
        reason=reason,
        per_dataset=per_dataset,
        shared_feature_space=shared_feature_space,
        requires_ortholog_mapping=requires_ortholog_mapping,
        requires_probe_collapse=requires_probe_collapse,
    )


def get_integration_plan(
    dataset_ids: list[str],
    design_factor: Optional[str] = None,
    test_group: Optional[str] = None,
    control_group: Optional[str] = None,
) -> dict:
    """
    Decide whether ``dataset_ids`` can be combined early, late, or not at all.

    Pure function of registry metadata — loads no expression data. Resolves each
    id to its manifest, then delegates to :func:`plan_for_manifests`.

    Parameters
    ----------
    dataset_ids:
        Two or more registered dataset identifiers. Fewer than two -> refuse
        (``NOT_MULTI``).
    design_factor, test_group, control_group:
        Optional. The contrast the caller intends to run. When supplied, Gate 6
        refuses (``CONFOUNDED_DESIGN``) if metadata shows no single cohort can
        express both arms. When omitted, design separability is deferred to the
        specialist's runtime check and is never refused here.

    Returns
    -------
    dict with keys: ``mode`` ("early"|"late"|"concordance"|"refuse"), ``reason``
    (non-empty, surfaced verbatim by the agent), ``shared_feature_space``,
    ``requires_ortholog_mapping``, ``requires_probe_collapse``, ``batch_key``,
    ``poolable_data_level``, ``per_dataset`` (each entry includes ``cohort_id``
    and ``variant``), ``refusal_rules_triggered``. ``mode == "concordance"``
    means the requested datasets are sibling variants of one cohort — compare
    them, do not combine.

    Raises
    ------
    ValueError if any dataset_id is not registered (message lists available ids).
    """
    from .registry import get_registry, load_manifest

    reg = get_registry()
    manifests: list["DatasetManifest"] = []
    for did in dataset_ids:
        if did not in reg:
            raise ValueError(
                f"Dataset '{did}' not found in registry. "
                f"Available datasets: {reg.list()}"
            )
        manifests.append(load_manifest(did))

    return plan_for_manifests(
        manifests,
        design_factor=design_factor,
        test_group=test_group,
        control_group=control_group,
    )
