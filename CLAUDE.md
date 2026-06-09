# biodata-registry — Architecture

Stable architecture reference. Current status → `memory.md`.

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
  __init__.py          — public API: get_registry(), load_manifest(), list_available_datasets()
  registry.py          — auto-discovers and indexes YAML manifests at import time
  manifest_schema.py   — typed DatasetManifest dataclass + controlled vocabularies
  server.py            — FastMCP server exposing 4 MCP tools
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

## The Four MCP Tools (server.py)

| Tool | What it does |
|------|-------------|
| `list_datasets` | List all dataset IDs, titles, modalities |
| `get_manifest` | Full manifest dict for a dataset |
| `get_prohibited_inferences` | Refusal rules — what agents must not claim |
| `get_contrast_definition` | Contrast definitions for a specific design_factor column |

Run the server: `python -m biodata_registry.server`

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
