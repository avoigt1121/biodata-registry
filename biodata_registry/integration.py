"""
Cross-dataset compatibility engine (ADR-0001 Phase 1, step 2).

``get_integration_plan`` decides whether a set of datasets can be combined

  * **early** — pool the expression matrices and fit one model with
    ``dataset_id`` as a batch covariate, or
  * **late** — analyze each dataset separately and meta-analyze the results, or
  * **refuse** — the datasets are incompatible for either route.

The decision is a **pure function of manifest metadata** — no data is loaded.
This deliberately keeps the registry metadata-pure: the *sample-level* confound
check (are both contrast arms actually populated in each cohort after
subsetting?) and the actual pooling / correction / meta-analysis happen later in
the specialist. See ADR-0001-decision-matrix.md ("Registry vs specialist").

Resolution order (first failing gate decides; short-circuit on ``refuse``)
--------------------------------------------------------------------------
1. arity        < 2 datasets                 -> refuse  (NOT_MULTI)
2. organism     mixed & no ortholog bridge   -> refuse  (CROSS_ORGANISM_NO_BRIDGE)
                mixed & bridgeable           -> requires_ortholog_mapping=True, continue
3. feature      no shared gene_symbol space  -> refuse  (NO_SHARED_FEATURE_SPACE)
4. modality     transcriptome + proteome     -> refuse  (CROSS_MODALITY)   [v1]
5. data_level   poolable & EQUAL on all       -> early-eligible; else -> late   (D3)
6. confound     a requested contrast cannot
                run in any single cohort     -> refuse  (CONFOUNDED_DESIGN)
                else early-eligible -> early; else -> late

``early`` -> ``late`` downgrades are **not** refusals — they carry a clear
``reason`` and an empty ``refusal_rules_triggered``.

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
CROSS_ORGANISM_NO_BRIDGE = "CROSS_ORGANISM_NO_BRIDGE"
NO_SHARED_FEATURE_SPACE = "NO_SHARED_FEATURE_SPACE"
CROSS_MODALITY = "CROSS_MODALITY"
CONFOUNDED_DESIGN = "CONFOUNDED_DESIGN"


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
    Does manifest metadata *positively* show the requested contrast is
    fully confounded with dataset (separable design)?

    Conservative on purpose. The contrast is separable only when, for the
    requested ``design_factor``, **no single cohort can express both arms** and
    every cohort's arm set is knowable from metadata. If any cohort declares the
    factor but lists no arms (allowed_values/contrasts absent), we cannot prove
    separation from metadata and defer to the specialist's runtime check
    (returns ``(False, "")``).

    Partial imbalance (one cohort has both arms, another is skewed) is *not*
    separation — that is exactly what the early-mode batch covariate handles.

    Returns ``(separable, detail)`` where ``detail`` summarises per-cohort arms.
    """
    wanted: Optional[set[str]] = None
    if test_group is not None and control_group is not None:
        wanted = {test_group, control_group}

    summary: dict[str, object] = {}
    states: list[Optional[bool]] = []  # True=can run, False=cannot, None=unknown
    for m in manifests:
        arms = _declarable_arms(m, design_factor)
        if not arms:
            if _declares_factor(m, design_factor):
                summary[m.dataset_id] = "<arms unspecified>"
                states.append(None)              # present but unknowable -> defer
            else:
                summary[m.dataset_id] = "<factor absent>"
                states.append(False)             # cannot supply either arm
            continue
        summary[m.dataset_id] = sorted(arms)
        if wanted is not None:
            states.append(wanted.issubset(arms))
        else:
            states.append(len(arms) >= 2)        # factor only -> need >=2 arms

    if any(s is True for s in states):
        return False, ""                         # a cohort can run it -> not broken
    if any(s is None for s in states):
        return False, ""                         # insufficient metadata -> defer
    detail = ", ".join(f"{k}={v}" for k, v in summary.items())
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
                    f"dataset: no single cohort declares both arms ({detail}). "
                    f"Pooling would perfectly confound the biological contrast "
                    f"with batch. Refusing."
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
    dict with keys: ``mode`` ("early"|"late"|"refuse"), ``reason`` (non-empty,
    surfaced verbatim by the agent), ``shared_feature_space``,
    ``requires_ortholog_mapping``, ``requires_probe_collapse``, ``batch_key``,
    ``poolable_data_level``, ``per_dataset``, ``refusal_rules_triggered``.

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
