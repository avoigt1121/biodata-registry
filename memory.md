# memory.md — biodata-registry Working State

Last updated: 2026-06-09

---

## Current State

Package is functional, tested, and imported by DecoupleRpy_Agent as the sole manifest source.
**16 manifests registered** (was 9 before 2026-06-09 session). All manifests validated.
All new h5ad files hosted at `anni-voigt/pdac-research-data` on HuggingFace.
All new manifests committed and pushed to `origin` (GitHub).

---

## Validated Manifest Status

### Original manifests (pre-2026-06-09)

| Dataset | Platform | feature_id_type | Survival | Notes |
|---------|----------|-----------------|----------|-------|
| `gse71729_moffitt` | Agilent 8x60K | gene_symbol | ❌ | Classical/basal subtypes |
| `gse28735_pdac` | Affymetrix Gene 1.0 ST (GPL6244) | entrez_id | ✅ | requires collapse |
| `gse16515_mayo` | Affymetrix U133+2 (GPL570) | normalized (linear) | ❌ | requires log2 before analysis |
| `gse62165_jiang` | Affymetrix U219 (GPL13667) | probe_id | ❌ | requires collapse |
| `gse71989_chen` | Affymetrix U133+2 (GPL570) | probe_id | ❌ | requires collapse |
| `tcga_paad` | Illumina HiSeq GDC STAR-Counts | gene_symbol | ✅ | raw_counts, Path A / DESeq2; 18.9% non-PDAC contamination |
| `paca_au_rnaseq` | Illumina HiSeq RSEM | gene_symbol | ✅ | ICGC PACA-AU; Bailey 2016 subtypes |
| `paca_au_array` | Affymetrix HuEx 1.0 ST | gene_symbol | ✅ | ICGC PACA-AU array version |
| `puleo_2018` | Affymetrix HuEx 1.0 ST | gene_symbol | ✅ | 309 samples; 5-subtype WholeTumorClass |

### New manifests added 2026-06-09

| Dataset | Platform | feature_id_type | Survival | Key Issues |
|---------|----------|-----------------|----------|------------|
| `gse15471_badea` | Affymetrix HG-U133+2 (GPL570) | probe_id | ❌ | 39 matched T/N pairs; "normal" = adjacent tissue NOT healthy |
| `gse21501_stratford` | Agilent two-color (GPL4133) | gene_symbol | ❌ | log ratio values; survival not in GEO; 35/132 unknown tissue type |
| `gse57495` | GPL15048 (Affymetrix HuEx 1.0 ST reannotated) | probe_id | ✅ OS (100%) | All PDAC tumors; stage IIA/IIB |
| `gse17891_collisson` | Affymetrix HG-U133+2 (GPL570) | probe_id | ❌ | Collisson subtypes NOT in GEO; 20/47 are cell lines |
| `paca_ca_rnaseq` | Illumina HiSeq RSEM | ensembl_gene_id | ✅ survivalA (81%) | ICGC Canadian; no subtype labels; 40 cell lines + metastatic included |
| `cptac_pda` | Illumina HiSeq RSEM TPM (GENCODE v34) | gene_symbol | ✅ OS (99%) | TPM not comparable to GEO cohorts without batch correction |
| `gse50827_nones` | Illumina HumanHT-12 V4.0 (GPL10558) | gene_symbol | ✅ OS (95%) | 103 primary PDAC; some Excel-corrupted gene symbols |

---

## Data Quality Flags / Known Issues Per Dataset

### gse21501_stratford
- Tissue type inferred from sample title (T suffix = tumor); 35/132 labelled "unknown"
- Survival data from Stratford 2010 paper IS NOT in GEO; not in h5ad
- Two-color Agilent array: log ratio values (range -11 to +11); negative values expected

### gse17891_collisson
- Collisson subtypes (QM / exocrine-like / classical) NOT deposited in GEO
- Must be sourced from Collisson 2011 Nature Medicine Table S1
- 20/47 samples are PDAC cell lines — filter before tumor-specific analyses
- Negative expression values possible (RMA log2 near-zero probes)

### paca_ca_rnaseq
- No Moffitt or Bailey subtype annotations — subtype classification requires separate step
- 262 samples include primary tumor (195), cell lines (40), metastatic (16), PDX (11)
- survivalB NOT encoded — only 47% of samples have data (below 80% quality threshold)
- ICGC data release version not available from pdacR v0.1.2

### cptac_pda
- RSEM TPM values NOT directly comparable to GEO or TCGA cohorts without batch correction
- 131/193 expression samples have matched clinical data
- RFS NOT encoded — only 53% of samples have data

### gse50827_nones
- Some gene symbols are Excel-corrupted date artifacts (e.g., '1-Dec' → DEC1, '1-Mar' → MARC1)
- No pathological stage data (all NA in GEO)

### gse15471_badea
- "Normal" samples are adjacent non-tumor pancreatic tissue from surgical resection
- Results must NOT be described as "tumor vs. healthy baseline"
- 3 patients have 4 samples (whole-tissue + microdissected per paper methods)

### Chan-Seng-Yue 2020 (COMPASS) — SKIPPED
- Could not find public GEO accession after thorough search
- Data appears to be EGA controlled-access (ICGC PACA-CA pathway)
- PACA-CA expression data already available as `paca_ca_rnaseq`
- COMPASS subtype labels can be applied to paca_ca_rnaseq once obtained from paper supplement

---

## What Was Done (2026-06-09)

### 8 datasets attempted, 7 successfully added
- Wrote Python assembly scripts for each dataset (in DecoupleRpy_Agent/scripts/)
- Installed GEOparse into DecoupleRpy_Agent .venv
- Downloaded 3 pdacR RDS files directly from GitHub (no R package install possible)
- Installed pyreadr (didn't work for pdacR lists) + data.table R package for fast CSV export
- Installed cptac Python package for CPTAC-PDA
- All h5ad files uploaded to `anni-voigt/pdac-research-data`
- All manifests pass `pytest tests/` (19 tests) and `dataset_validate_manifest_against_data`
- Each commit pushed to GitHub after validation

### No tool code modified
- Zero changes to DecoupleRpy_Agent tool code
- Zero changes to biodata-registry schema code
- Manifest-driven architecture worked as designed — adding datasets required only YAML + h5ad

---

## Process Notes (for future sessions)

- pdacR R package cannot be installed on this machine (illuminaHumanv4.db + hgu219.db fail)
  → Workaround: download individual .rds files from GitHub and use Rscript + data.table
- Gene symbol type mismatches: R integer column IDs require .str.lstrip("V").astype(int)
- Agilent GPL4133 probe IDs are integers — type-safe join required for gene symbol mapping
- CPTAC clinical tables have duplicate column names — dedup before building AnnData
- GEO two-color arrays (GPL4133): log ratio values, negative values expected and valid

---

## Known Issues / TODOs

### 1. pdacR install broken on this machine — LOW PRIORITY
illuminaHumanv4.db and hgu219.db fail to install via BiocManager on Bioc 3.22 / R 4.5.3.
Workaround (individual .rds downloads) works fine for data extraction.

### 2. No HF deployment for biodata-registry — LOW PRIORITY
Not currently needed since DecoupleRpy_Agent imports directly.

### 3. Tests only cover schema validation — LOW PRIORITY
No tests verify column values against live GEO/HF data.

### 4. TCGA-PAAD sample curation — MEDIUM PRIORITY
18.9% non-PDAC contamination. Curated barcode list added to manifest (Knudsen 2019).

### 5. Collisson subtypes missing — MEDIUM PRIORITY
gse17891_collisson has no subtype labels. Requires manual curation from Collisson 2011 Table S1.

### 6. Chan-Seng-Yue 2020 COMPASS subtypes — LOW PRIORITY
Could not find public GEO deposit. PACA-CA data is present; COMPASS labels need paper supplement.

### 7. gse50827_nones Excel-corrupted gene symbols — LOW PRIORITY
Some gene names are date artifacts (e.g., '1-Dec', '1-Mar'). Documented in manifest limitations.
Fix requires re-mapping through Ensembl or original GPL10558 annotation.

---

## Git State

| Remote | URL |
|--------|-----|
| `origin` | `github.com/avoigt1121/biodata-registry` |

Branch: `main`. Up to date with origin (last push: 978599f).
16 manifests registered. 7 new manifests added in 2026-06-09 session.
