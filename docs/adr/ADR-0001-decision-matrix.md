# ADR-0001 Decision Matrix — `get_integration_plan`

**Status:** Implemented & released — Phase 1 shipped (registry side).
0.1.2 first cut (engine + 5th MCP tool), 0.1.3 Gate 6 confound hardening
(Case 3), 0.1.6 same-cohort gate (`concordance` / `DUPLICATE_COHORT`). This
document tracks the engine as shipped in **0.1.6**.
**Home of the logic:** `biodata_registry/integration.py` (this repo — the
authoritative source of truth for the decision).
**Parent ADR (feature context, spans three repos):**
[`DecoupleRpy_Agent/docs/adr/ADR-0001-cross-dataset-integration.md`](../../../DecoupleRpy_Agent/docs/adr/ADR-0001-cross-dataset-integration.md)
and its companions (`ADR-0001-implementation-plan.md`, `ADR-0001-spinoff-tasks.md`).

> **Why this file lives here.** The cross-dataset integration *feature* spans
> three repos and its ADR series is anchored in `DecoupleRpy_Agent` (the bulk of
> the work — pooling, batch correction, meta-analysis, concordance — is
> specialist-side). But the **decision matrix** specifies *this* repo's engine
> (`integration.py`), so the authoritative, current copy belongs here, next to the
> code it describes. The copy under `DecoupleRpy_Agent/docs/adr/` is the original
> **Phase-0 spec** ("needs sign-off before Phase 1 coding") and predates the
> `concordance` mode, the same-cohort gate, and the implemented `design_factor`
> arguments — **this version supersedes it.** Keep them from drifting: when the
> engine changes, update *this* file; the agent's copy should point here.

This spec pins exactly how `get_integration_plan(dataset_ids, …)` decides between
**early** (pool the expression), **late** (meta-analyze results), **concordance**
(sibling variants of one cohort — compare, don't combine), and **refuse**. It
resolves delta **D3**: eligibility keys on `data_level`, not the coarse A/B
`analysis_path`. It is implemented as a pure function of manifest metadata and is
unit-tested as such (`tests/test_integration_plan.py`).

---

## Inputs consumed (all from the manifest)

Per dataset, from `DatasetManifest` (`biodata_registry/manifest_schema.py`):

| Field | Used for |
|---|---|
| `cohort_id`, `variant` | **same-cohort gate** (Gate 1b) — sibling quantifications of one cohort (e.g. the GSE205154 TPM/counts/TMM trio) |
| `organism` | cross-organism gate (Gate 2) |
| `feature_id_type` | shared feature-space check (Gate 3): `probe_id / gene_symbol / ensembl_gene_id / entrez_id / protein_id` |
| `feature_mapping.requires_collapse` | whether `probe_id` can collapse to `gene_symbol` |
| `modality` | cross-modality gate (Gate 4): `proteomics` vs transcriptomics |
| `data_level` | poolability (Gate 5 / D3): `raw_counts / log_expression / log_ratio / normalized / tpm / fpkm / protein_abundance` |
| `analysis_path` (derived) | reported in `per_dataset` as a coarse cross-check; **not** the eligibility key |
| `group_columns`, `metadata_columns[factor].allowed_values` (minus `missing_values`), `default_contrasts` | metadata-level confound feasibility (Gate 6): does each cohort declare the requested factor and its arms? |

> The registry sees **metadata only**. The *sample-level* confound check (are both
> contrast arms actually populated in each cohort after subsetting?) happens later
> in the specialist when it loads the data — see [§ Registry vs specialist](#registry-vs-specialist).

## Signature & output

```python
get_integration_plan(
    dataset_ids: list[str],
    design_factor: str | None = None,   # the contrast the caller intends to run
    test_group: str | None = None,      # (Gate 6 only fires when these are given)
    control_group: str | None = None,
) -> {
  "mode": "early" | "late" | "concordance" | "refuse",
  "reason": str,                        # human-readable, non-empty, agent surfaces verbatim
  "shared_feature_space": str | None,   # e.g. "gene_symbol" (the common space)
  "requires_ortholog_mapping": bool,
  "requires_probe_collapse": bool,
  "batch_key": "dataset_id",            # obs column used as batch covariate when early
  "poolable_data_level": str | None,    # the shared level when mode == "early"
  "per_dataset": [
    {"dataset_id", "organism", "modality", "data_level", "analysis_path",
     "feature_id_type", "requires_collapse", "cohort_id", "variant"}
  ],
  "refusal_rules_triggered": list[str],  # stable codes (see taxonomy); empty unless mode == "refuse"
}
```

`plan_for_manifests(manifests, design_factor=None, test_group=None,
control_group=None)` is the underlying pure engine — same logic, takes
already-constructed `DatasetManifest` objects so it is unit-testable without the
registry. `get_integration_plan` resolves ids → manifests, then delegates to it.
An unregistered id raises `ValueError` (message lists the available ids).

---

## Resolution order (first failing gate decides)

Evaluate gates **in order**. The first that fails sets `refuse` (or, for the
data-level gate, downgrades `early`→`late`). Short-circuit on `refuse`.

```
1.  arity     < 2 datasets                       -> refuse  (NOT_MULTI)
1b. cohort    >=2 requested datasets share a cohort_id (same samples, diff. units):
                all requested are one cohort      -> concordance
                siblings mixed with other datasets-> refuse  (DUPLICATE_COHORT)
2.  organism  mixed & no ortholog bridge          -> refuse  (CROSS_ORGANISM_NO_BRIDGE)
                mixed & bridgeable                 -> requires_ortholog_mapping=True, continue
3.  feature   no shared/derivable gene_symbol space-> refuse (NO_SHARED_FEATURE_SPACE)
4.  modality  mixed transcriptome/proteome         -> refuse (CROSS_MODALITY)   [v1]
5.  data_level poolable & EQUAL on all             -> early-eligible; else -> late   (D3)
6.  confound  (only if design_factor supplied) a requested contrast is
                confounded with dataset            -> refuse  (CONFOUNDED_DESIGN)
              else: early-eligible -> early; else -> late
```

### Gate 1 — arity

Fewer than 2 datasets → `refuse` (`NOT_MULTI`). Integration is meaningless for a
single cohort.

### Gate 1b — same-cohort variants (the concordance gate)

Two manifest fields mark datasets that are the **same samples in different
quantifications**: `cohort_id` (the shared cohort) and `variant` (the
quantification label, e.g. `tpm` / `counts` / `tmm`). If ≥2 requested datasets
share a `cohort_id`:

- **The whole request is one cohort's variants** → `mode = "concordance"`. They
  must **not** be pooled or meta-analyzed — that double-counts the cohort.
  Meta-analysis assumes *independent* cohorts; combining identical samples makes
  Stouffer inflate the combined score by ≈√N, and Cochran's Q / I² collapse to 0
  by construction (zero heterogeneity is *guaranteed*, not evidence of
  robustness). The correct framing is a **normalization concordance / sensitivity
  check**: run each variant separately, then compare descriptively (Pearson/
  Spearman on scores, sign-concordance, overlap of significant calls).
- **Siblings mixed with independent datasets** → `refuse` (`DUPLICATE_COHORT`).
  Pick exactly one variant per cohort first, then re-request.

**This gate runs *before* the `data_level` gate on purpose.** Siblings differ
*only* in quantification, so without it a TPM+TMM request (`tpm` ≠ `normalized`)
would fall through Gate 5 to `late` and be silently meta-analyzed — exactly the
double-counting we must prevent. `concordance` is **not** a refusal; it carries an
empty `refusal_rules_triggered`.

### Gate 2 — organism

- All `organism` equal → continue, `requires_ortholog_mapping = False`.
- Mixed (e.g. `human` + `mouse`) → bridgeable iff **every** cohort can reach the
  `gene_symbol` space (orthology bridges symbol↔symbol). If so, set
  `requires_ortholog_mapping = True` and continue (the specialist performs the
  mapping). If any cohort cannot reach gene symbols → `refuse`
  (`CROSS_ORGANISM_NO_BRIDGE`).

### Gate 3 — shared feature space

Target space is `gene_symbol` (decoupleR networks are keyed on symbols).

| Per-dataset `feature_id_type` | Reaches `gene_symbol`? |
|---|---|
| `gene_symbol` | yes (direct) |
| `ensembl_gene_id` / `entrez_id` | yes (id-map to symbol) |
| `probe_id` + `requires_collapse=True` | yes (collapse first → sets `requires_probe_collapse=True`) |
| `probe_id` + `requires_collapse` not set | **no** usable mapping → `refuse` |
| `protein_id` | reaches gene space via protein→gene map; the transcriptome/proteome split is **Gate 4's** job, not this one |

If every cohort reaches `gene_symbol`, set `shared_feature_space="gene_symbol"`
and `requires_probe_collapse` = (any dataset needed a probe collapse). If any
cannot → `refuse` (`NO_SHARED_FEATURE_SPACE`).

### Gate 4 — modality (v1 conservative)

Pooling expression **across modalities** (RNA transcriptomics + mass-spec
proteomics) is out of scope for v1. A request mixing `proteomics` with any
transcriptomic modality → `refuse` (`CROSS_MODALITY`). A shared cross-modality
meta-analysis envelope is future work. Same-side requests continue.

### Gate 5 — `data_level` poolability (resolves D3)

**Early integration requires the *same* `data_level` on every dataset, and that
level must be in the poolable set.** Mixed levels are never pooled — they go
`late`.

| `data_level` (must match on all) | Early-eligible? | Combine route when early |
|---|---|---|
| `raw_counts` | ✅ | Path A — DESeq2 `~ batch + condition` |
| `log_expression` | ✅ | Path B — limma, batch in design |
| `log_ratio` | ✅ | Path B — limma, batch in design (two-color arrays) |
| `tpm` | ✅ | Path B — `log2(tpm+1)` → limma + batch |
| `fpkm` | ✅ | Path B — `log2(fpkm+1)` → limma + batch |
| `normalized` | ❌ | scale unspecified → **never early**, even when equal → `late` |
| `protein_abundance` | ❌ | proteomics → handled at Gate 4 |
| **any mismatch across datasets** | ❌ | → `late` |

Implemented as `POOLABLE_EARLY_LEVELS = {raw_counts, log_expression, log_ratio,
tpm, fpkm}` and `NEVER_EARLY_LEVELS = {normalized, protein_abundance}`.

Rationale: `raw_counts` is the only Path-A level; within Path B, only *identical*
quantification scales are comparable enough to batch-correct. `normalized`
("scale unspecified", per `manifest_schema.py`) is deliberately excluded from
early pooling — we cannot guarantee comparable scale, so it always meta-analyzes.
This is stricter than "both A or both B" and is the safe default; loosen only with
evidence. When early-eligible, set `poolable_data_level` to the shared level.

### Gate 6 — confound (metadata-level only; opt-in)

**Only fires when the caller supplies the contrast** via `design_factor`
(+ optionally `test_group` / `control_group`). Without it the registry cannot tell
which design is at stake, so design separability is deferred to the specialist and
this function never fabricates a `CONFOUNDED_DESIGN` refusal.

Arms a cohort can declare for `factor` are drawn from
`metadata_columns[factor].allowed_values` (minus that column's `missing_values`)
and from any `default_contrasts` whose `design_factor` is `factor`. A contrast is
confounded with dataset — `refuse` (`CONFOUNDED_DESIGN`) — in two cases:

1. **A cohort contributes *neither* arm.** The factor is absent from its metadata,
   or its declared arms are disjoint from the requested `{test, control}` pair. The
   contrast then lives in only a subset of the requested datasets, so the
   "combined" result would be a single cohort relabelled. *(This is the Case-3
   guard added in 0.1.3 — e.g. a Bailey-subtype contrast across a Bailey-labelled
   cohort + one with no Bailey labels.)* A definite absence is decisive even if
   another cohort is "unknown".
2. **No single cohort declares both arms** (perfectly split design): each cohort
   supplies only one arm, so arm is perfectly aliased with dataset.

**Not** a refusal (conservative on purpose):

- **Partial imbalance** — one cohort supplies both arms, another is skewed but
  still contributes an arm. That is exactly what the early-mode batch covariate
  handles.
- **Factor declared but arms unspecified** (`allowed_values`/contrasts absent) —
  *unknown*, not absent. We cannot prove confounding from metadata, so defer to the
  specialist's runtime check rather than refuse.

If not separable: early-eligible → `early`; else → `late`.

---

## Refusal-code taxonomy

Stable codes in `refusal_rules_triggered` (the agent renders `reason` to the user):

| Code | Meaning |
|---|---|
| `NOT_MULTI` | fewer than 2 datasets supplied |
| `DUPLICATE_COHORT` | ≥2 quantifications of one cohort requested alongside independent datasets — pick one variant per cohort |
| `CROSS_ORGANISM_NO_BRIDGE` | organisms differ and orthology cannot bridge the features |
| `NO_SHARED_FEATURE_SPACE` | no common/derivable `gene_symbol` space |
| `CROSS_MODALITY` | mixed transcriptome/proteome (v1) |
| `CONFOUNDED_DESIGN` | a cohort cannot supply the requested contrast → design separable from dataset |

Non-refusals carry an **empty** `refusal_rules_triggered`:

- **`concordance`** — sibling variants of one cohort; compare, don't combine.
- **`early`→`late` downgrades** — e.g. *"Mixed data_level across datasets
  ([log_expression, raw_counts]) — pooling raw values across different
  quantification scales is invalid; meta-analyzing per-dataset results instead."*

## Registry vs specialist <a name="registry-vs-specialist"></a>

The decision is **split** so the registry stays metadata-pure:

- **Registry (`get_integration_plan`)** — everything above: same-cohort, organism,
  feature space, modality, `data_level` poolability, and the *metadata-level*
  confound feasibility. Pure function of manifests; unit-testable; no data loaded.
- **Specialist (Phase 1/2 workflows in `DecoupleRpy_Agent`)** — the *sample-level*
  confound check after loading data (are both arms actually populated per cohort,
  post-`subset_query`?) and the actual pooling/correction/meta-analysis/concordance
  computation. If the runtime check finds a separation the manifest could not
  reveal, the specialist refuses with the same `CONFOUNDED_DESIGN` reason.

This preserves the ADR invariant — the *coordinator* never decides semantics; the
registry decides compatibility, the specialist acts and does the runtime guard.

The "revisit" hook stands: if metadata is insufficient for the confound check, add
an optional manifest field (`known_batch_confounds` / `integration_notes`) rather
than hardcoding pairs.

---

## Worked examples (real registered datasets)

| Request | Gate that fires | Verdict |
|---|---|---|
| `gse205154_sears` (tpm) + `_counts` (raw_counts) + `_tmm` (normalized) — all `cohort_id=gse205154` | G1b, whole request is one cohort | **concordance** — run each variant, compare descriptively (never pool/meta-analyze) |
| `gse205154_sears` + `gse205154_sears_tmm` (two siblings, nothing else) | G1b, whole request is one cohort | **concordance** |
| `gse205154_sears` + `gse205154_sears_tmm` + `tcga_paad` (siblings mixed with an independent dataset) | G1b, siblings + other | **refuse** — `DUPLICATE_COHORT` (pick one Sears variant first) |
| `tcga_paad` (raw_counts, gene_symbol) + `paca_au_rnaseq` (raw_counts, gene_symbol) | G5 equal `raw_counts` | **early** — DESeq2 `~batch+condition`, `shared_feature_space="gene_symbol"`, `requires_probe_collapse=False` |
| `gse71729_moffitt` (log_expression) + `tcga_paad` (raw_counts) | G5 mismatch | **late** — meta-analyze per-dataset activity envelopes (the microarray×RNA-seq case) |
| Two `normalized` datasets (equal level) | G5 — `normalized` ∈ never-early | **late** — scale unspecified, never pooled |
| `paca_au_rnaseq` (Bailey-labelled) + `tcga_paad` (no Bailey labels), `design_factor` = Bailey subtype | G6, a cohort contributes neither arm | **refuse** — `CONFOUNDED_DESIGN` (Case 3) |
| any human + any mouse with no ortholog route | G2 | **refuse** — `CROSS_ORGANISM_NO_BRIDGE` (or continue with `requires_ortholog_mapping=True` if bridgeable) |
| a single dataset | G1 | **refuse** — `NOT_MULTI` |

> All current registered datasets are human, so the cross-organism row is
> illustrative. Confirm any per-dataset `data_level` / `feature_id_type` against
> the manifest when adding tests.

## Unit-test checklist (`tests/test_integration_plan.py`)

- equal `raw_counts` → `early`; equal `log_expression` → `early`
- mixed `raw_counts` + `log_expression` → `late`
- equal `normalized` → `late` (the deliberate never-early exclusion)
- `probe_id` + `requires_collapse=False` → `refuse / NO_SHARED_FEATURE_SPACE`
- `probe_id` + `requires_collapse=True` → reachable, `requires_probe_collapse=True`
- human + mouse, no bridge → `refuse / CROSS_ORGANISM_NO_BRIDGE`
- 1 dataset → `refuse / NOT_MULTI`
- **all siblings of one `cohort_id` → `concordance`** (empty `refusal_rules_triggered`)
- **siblings + an independent dataset → `refuse / DUPLICATE_COHORT`**
- **Gate 6**: factor-absent → refuse; disjoint-arms → refuse; real
  `paca_au_rnaseq` + `tcga_paad` Bailey case → refuse; partial-imbalance →
  not-refused; no `design_factor` supplied → never `CONFOUNDED_DESIGN`
- every verdict carries a non-empty `reason`

---

## Change log

| Release | Change |
|---|---|
| **0.1.2** (2026-06-19) | Engine first cut — `get_integration_plan` + 5th MCP tool; early/late/refuse with the D3 `data_level` poolability rule (ADR-0001 T2). |
| **0.1.3** (2026-06-19) | Gate 6 confound hardening — refuse when a cohort can supply *neither* arm (Case 3), not only the perfectly-split case. |
| **0.1.6** (source 2026-06-22; release pending) | Same-cohort gate (Gate 1b): `cohort_id`/`variant` fields + `concordance` mode + `DUPLICATE_COHORT` refusal; `per_dataset` entries gain `cohort_id`/`variant`. |

## References

- Parent ADR & companions (feature context, agent-side Mode A/B work):
  `DecoupleRpy_Agent/docs/adr/ADR-0001-cross-dataset-integration.md`,
  `…-implementation-plan.md`, `…-spinoff-tasks.md`.
- Engine: `biodata_registry/integration.py`. Schema: `manifest_schema.py`
  (compatibility fields, controlled vocabularies). MCP surface:
  `server.py` (`get_integration_plan` tool).
- decoupleR (Badia-i-Mompel et al.), *Bioinformatics Advances* 2022 — footprint
  activity methods transfer across platforms, which is why the activity layer is
  the safest place to combine heterogeneous cohorts (`late`).
