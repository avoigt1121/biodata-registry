# biodata-registry — Architecture

Stable architecture reference. Current status → `memory.md`.

---

## Memory maintenance (after every commit)

These status files drift unless updated at commit time. After any `git commit` in this
repo (GitHub-only — no HF Space), update whatever that commit changed, and skip what it
didn't:

- `memory.md` — current status / what just changed
- `TODO.md` / `REGISTRY_TODO_PLANS.md` — task status (move done items, add new ones)
- `/Users/annivoigt/Documents/GitHub/SHOWCASE_STATUS.md` — the cross-repo rollup; update especially when a manifest bump needs to be re-pinned in a consuming repo
- `CLAUDE.md` (this file) — only when the architecture itself changes (rare)

A PostToolUse hook (`~/.claude/hooks/remind-memory-sync.py`, wired in
`~/.claude/settings.json`) prints this checklist automatically after each commit. It only
*reminds* — the edits are still done by hand.

---

## What This Repo Is

A **pip-installable Python package** that provides a shared dataset manifest registry
for bioinformatics agents. It is the authoritative source of truth for dataset
semantics — what each dataset is, what analysis is allowed, what is refused.

It also exposes a **FastMCP server** so agent processes can query dataset metadata
over MCP without importing the package directly.

**This is a shared library, not an application.** It has no UI.

---

## Package Structure

```
biodata_registry/
  __init__.py          — public API: get_registry(), load_manifest(), list_available_datasets(), get_integration_plan()
  registry.py          — auto-discovers and indexes YAML manifests at import time
  manifest_schema.py   — typed DatasetManifest dataclass + controlled vocabularies
  integration.py       — get_integration_plan(): pure cross-dataset compatibility engine (early/late/refuse)
  server.py            — FastMCP server exposing 5 MCP tools
  manifests/
    gse71729_moffitt.yaml   ← fully annotated reference manifest
    gse28735_pdac.yaml
    gse16515_mayo.yaml
    gse62165_jiang.yaml
    gse71989_chen.yaml

tests/
  test_registry.py     — validates all manifests load correctly
```

---

## The Five MCP Tools (server.py)

| Tool | What it does |
|------|-------------|
| `list_datasets` | List all dataset IDs, titles, modalities |
| `get_manifest` | Full manifest dict for a dataset |
| `get_prohibited_inferences` | Refusal rules — what agents must not claim |
| `get_contrast_definition` | Contrast definitions for a specific design_factor column |
| `get_integration_plan` | Decide if datasets combine early (pool) / late (meta-analyze) / concordance (same-cohort sibling variants — compare, don't combine) / refuse — pure metadata function (ADR-0001) |

Run the server: `python -m biodata_registry.server`

### Cross-dataset integration (`integration.py`, ADR-0001 Phase 1)

`get_integration_plan(dataset_ids, design_factor=None, test_group=None, control_group=None)`
is a **pure function of manifest metadata** — it loads no expression data. It runs a
decision sequence (arity → **same-cohort** → organism/ortholog bridge → shared `gene_symbol`
feature space → modality → `data_level` poolability [D3] → metadata-level confound) and returns
`mode` (`early`/`late`/`concordance`/`refuse`), a human-readable `reason`, and the flags an agent needs
(`shared_feature_space`, `requires_probe_collapse`, `requires_ortholog_mapping`,
`batch_key`, `poolable_data_level`, `per_dataset` [now incl. `cohort_id`/`variant`],
`refusal_rules_triggered`).

Same-cohort gate (0.1.6): two optional manifest fields, `cohort_id` and `variant`, mark
datasets that are the **same samples in different quantifications** (e.g. the GSE205154
TPM/counts/TMM trio). The gate runs **before** the `data_level` gate: if ≥2 requested
datasets share a `cohort_id`, the engine returns `concordance` (when the whole request is
one cohort's variants — run each separately and compare descriptively; this is a
normalization sensitivity check, not a combine) or refuses with `DUPLICATE_COHORT` (when
siblings are mixed with independent datasets — pick one variant per cohort first). Without
it, a TPM+TMM request would fall through to `late` and be meta-analyzed, double-counting the
identical samples. `concordance` is **not** a refusal (empty `refusal_rules_triggered`).

Key rule (D3): early pooling requires the **same** `data_level` on every dataset, and that
level must be poolable (`raw_counts`/`log_expression`/`log_ratio`/`tpm`/`fpkm`).
`normalized` and `protein_abundance` are never pooled (→ `late`). The optional contrast
args drive the confound gate; without them the design-separability check is deferred to the
specialist at runtime (registry stays metadata-pure). `pure plan_for_manifests()` is the
underlying engine, unit-testable against constructed `DatasetManifest` objects.

---

## Adding a New Dataset

1. Create `biodata_registry/manifests/<dataset_id>.yaml`
2. Required fields: `dataset_id`, `title`, `accession`, `organism`, `modality`,
   `platform`, `data_level`, `feature_id_type`, `expression_source`, `metadata_source`,
   `group_columns`, `valid_workflows`, `limitations`
3. Auto-discovered at import — no code changes needed
4. Run `pytest tests/` to verify it loads

See `gse71729_moffitt.yaml` as the fully annotated reference example.

---

## Controlled Vocabularies

- `modality`: `bulk_microarray`, `bulk_rnaseq`, `sc_rnaseq`, `spatial_rnaseq`, `proteomics`
- `data_level`: `raw_counts`, `log_expression`, `log_ratio`, `normalized`, `tpm`, `fpkm`, `protein_abundance`
- `feature_id_type`: `probe_id`, `gene_symbol`, `ensembl_gene_id`, `entrez_id`, `protein_id`

---

## Relationship to DecoupleRpy_Agent

**Intent**: DecoupleRpy_Agent should `pip install -e biodata-registry` and import
manifests from this package rather than maintaining its own copy.

**Current reality**: DecoupleRpy_Agent has its own duplicate manifest copies at
`src/datasets/manifests/`. The biodata-registry versions are more validated
(confirmed column names from actual GEO data). The duplication is a known issue.

**This repo is the authoritative source.** When manifests differ between repos,
prefer this repo's version.

---

## Deployment

- GitHub only: `github.com/avoigt1121/biodata-registry`
- No HF Space — consumed as a pip package
- Install: `pip install -e /path/to/biodata-registry`

---

## Key Design Decision

**Why a separate package instead of embedding manifests in each agent?**
Manifests encode refusal rules, prohibited inferences, and analysis constraints.
If each agent maintained its own copy, they'd diverge. A shared package means one
update propagates to every agent that installs it.
