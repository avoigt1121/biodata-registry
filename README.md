# biodata-registry

A pip-installable Python package that provides a YAML-based dataset manifest registry for bioinformatics agents. It also exposes a FastMCP server so agent processes can query dataset metadata over MCP.

## What it does

- Discovers and indexes dataset manifests (one YAML file per dataset) at import time
- Validates manifests against a typed schema (`DatasetManifest`)
- Ships with the Moffitt et al. 2015 PDAC bulk microarray dataset as the first entry
- Exposes registry tools over MCP via a FastMCP server

## Installation

```bash
pip install -e /path/to/biodata-registry
```

Or from within the repo directory:

```bash
pip install -e .
```

## Python usage

```python
from biodata_registry import get_registry, load_manifest, list_available_datasets

# List all registered datasets
datasets = list_available_datasets()
# [{'dataset_id': 'gse71729_moffitt', 'title': '...', 'modality': 'bulk_microarray', ...}]

# Get a typed manifest
manifest = load_manifest("gse71729_moffitt")
print(manifest.organism)          # 'human'
print(manifest.analysis_path)     # 'B'  (log_expression → Path B)
print(manifest.default_contrasts) # list of contrast dicts

# Raw registry access
reg = get_registry()
raw = reg.get("gse71729_moffitt")  # dict or None
print(reg.list())                   # ['gse71729_moffitt']
```

## Running the MCP server

```bash
python -m biodata_registry.server
```

The server exposes four MCP tools:

| Tool | Description |
|---|---|
| `list_datasets` | List all dataset IDs with title and modality |
| `get_manifest` | Return the full manifest dict for a dataset |
| `get_prohibited_inferences` | Return refusal rules from a manifest |
| `get_contrast_definition` | Return contrast metadata for a specific column |

## Adding a new dataset

1. Create a YAML file in `biodata_registry/manifests/<dataset_id>.yaml`.
2. The file must contain at minimum: `dataset_id`, `title`, `accession`, `organism`, `modality`, `platform`, `data_level`, `feature_id_type`, `expression_source`, `metadata_source`, `group_columns`, `valid_workflows`, `limitations`.
3. The registry auto-discovers it on next import — no code changes needed.
4. Run `python -m pytest tests/` to verify the new manifest loads correctly.

See `biodata_registry/manifests/gse71729_moffitt.yaml` for a fully annotated example.

## Schema reference

Manifest fields are documented in `biodata_registry/manifest_schema.py`. Key controlled vocabularies:

- `organism`: `human`, `mouse`
- `modality`: `bulk_microarray`, `bulk_rnaseq`, `sc_rnaseq`, `spatial_rnaseq`, `proteomics`
- `data_level`: `raw_counts`, `log_expression`, `log_ratio`, `normalized`, `tpm`, `fpkm`, `protein_abundance`
- `feature_id_type`: `probe_id`, `gene_symbol`, `ensembl_gene_id`, `entrez_id`, `protein_id`
