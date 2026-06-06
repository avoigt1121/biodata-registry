# memory.md — biodata-registry Working State

Last updated: 2026-06-06

---

## Current State

Package is functional, tested, and imported by DecoupleRpy_Agent as the sole manifest source.
6 manifests registered. All GEO manifests fully validated. TCGA-PAAD uses GDC STAR-Counts
raw counts (Path A / DESeq2), served from pre-assembled HF h5ad.

Last commit: `55be448` — "Add DESeq2 plain-language explanation to tcga_paad reporting_rules"

---

## Validated Manifest Status

| Dataset | Platform | Column names confirmed | Values confirmed | Survival data | Notes |
|---------|----------|----------------------|-----------------|---------------|-------|
| `gse71729_moffitt` | Agilent 8x60K | ✅ | ✅ | ❌ | gene_symbol, no collapse |
| `gse28735_pdac` | Affymetrix Gene 1.0 ST (GPL6244) | ✅ | ✅ ("T"/"N") | ✅ | entrez_id, requires collapse |
| `gse16515_mayo` | Affymetrix U133+2 (GPL570) | ✅ | ✅ | ❌ | normalized (linear scale), requires log2 before analysis |
| `gse62165_jiang` | Affymetrix U219 (GPL13667) | ✅ | ✅ | ❌ | probe_id, requires collapse |
| `gse71989_chen` | Affymetrix U133+2 (GPL570) | ✅ | ✅ | ❌ | probe_id, requires collapse |
| `tcga_paad` | Illumina HiSeq (GDC STAR-Counts, hg38/GENCODE v36) | ✅ | ✅ (from real GDC download) | ✅ (os_event/os_days via join) | gene_symbol, raw_counts, Path A / DESeq2; HF-hosted h5ad |

---

## What Was Done (2026-06-05)

### TCGA-PAAD manifest added
- `tcga_paad.yaml`: UCSC Xena HiSeqV2, log2(RSEM+1) normalized, gene symbols, ~178 samples
- Verified against real Xena download: 178 samples × 20,530 genes, KRAS present, normalized floats
- Clinical data: `PAAD_clinicalMatrix` (no .gz — the .gz URL returns 403; correct URL confirmed)
- Survival endpoints: os_event/os_days derived by `decoupler_join_clinical_metadata`
- Prominently encodes 18.9% non-PDAC contamination (Knudsen 2019, PMC6357157)
- Blocks DESeq2, tumor-vs-normal DE, uncurated survival in refusal_rules
- `VALID_COLUMN_ROLES` in `manifest_schema.py` (DecoupleRpy_Agent) updated to add `clinical` role
  — was a pre-existing gap also present in `gse28735_pdac`

---

## Known Issues / TODOs

### ~~1. DecoupleRpy_Agent does not import this package~~ — RESOLVED (2026-06-05)
Local manifest copies in DecoupleRpy_Agent removed. `biodata-registry` installed via `pip install -e`
and wired as the sole manifest source in `registry.py`.

### ~~3. Manifest sync drift~~ — RESOLVED (2026-06-05)
Both repos now use this package as authoritative source. No drift possible.

### 2. No HF deployment — LOW PRIORITY
The FastMCP server has never been deployed standalone. Not currently needed since
DecoupleRpy_Agent imports this package directly.

### 4. Tests only cover schema validation — LOW PRIORITY
`test_registry.py` verifies manifests load against schema. No tests verify column names/values
against live GEO data. The integration tests in DecoupleRpy_Agent serve this purpose instead.

### ~~5. GDC STAR-Counts for TCGA-PAAD~~ — RESOLVED (2026-06-06)
`tcga_paad.yaml` now uses raw_counts from GDC STAR-Counts pipeline (Path A / DESeq2).
Expression served from pre-assembled h5ad at `anni-voigt/pdac-research-data` on HF (49 MB).
gene_symbol feature IDs; Ensembl IDs in adata.var['ensembl_id'].

### 6. TCGA-PAAD sample curation — MEDIUM PRIORITY (tracked in DecoupleRpy_Agent memory.md)
18.9% of samples are non-PDAC (Knudsen 2019, PMC6357157). Currently documented only in
refusal_rules/limitations. Once a curated barcode list is obtained, add it as:
- A `curated_sample_list` field, or
- A `subset_query` on `sample_type == "Primary Tumor"` plus a verified barcode exclusion list

---

## Git State

| Remote | URL |
|--------|-----|
| `origin` | `github.com/avoigt1121/biodata-registry` |

Branch: `main`. Ahead of origin by 3 commits (TCGA-PAAD + prior session work).
Not yet pushed.
