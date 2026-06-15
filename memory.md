# memory.md — biodata-registry Working State

Last updated: 2026-06-14

---

## Current State

Package is functional, tested, and imported by DecoupleRpy_Agent as the sole manifest source.
**16 manifests registered**, all validated (0 errors).
**All 16 now use `expression_source.type: url` (precomputed h5ad)** — full
load-path parity achieved 2026-06-12 (Precompute Cache Phase 1). All h5ad
files are hosted at `anne-voigt/pdac-research-data` on HuggingFace (migrated
from `anni-voigt` 2026-06-12 — transfer complete, no `anni-voigt` references
remain).
Latest commit `1074739` pushed to `origin` (GitHub); pinned in
DecoupleRpy_Agent's `requirements.txt`.

**Registry origin/main = `dfbf8c4`** (pushed 2026-06-14). Recent work since the
status doc: live-data test harness (`e836605`), COMPASS limitation (`d21e03b`),
Collisson subtypes (`dfbf8c4`). DecoupleRpy_Agent `requirements.txt` pin bumped to
`dfbf8c4` and committed **locally only** (`227add0`) — NOT pushed/deployed (its
origin is the HF Space). Deploy when ready by pushing DecoupleRpy_Agent origin.

Note: the DecoupleRpy_Agent `.venv` had `pypdf` + `xlrd` pip-installed this session
(used by the Collisson annotation script / supplement parsing); not in any
requirements file.

---

## What Was Done (2026-06-14)

### Bailey 2016 / Puleo 2018 stress test — bug found and fixed

Downloaded the real hosted h5ad files for `paca_au_rnaseq`, `paca_au_array`,
`puleo_2018` and ran `validate_manifest_against_data` against live data
(previously only schema-validated, never run against actual data).

**Bug found (all 3 manifests)**: `default_contrasts.subset_query` was written
as `"obs['membership.ordered'].isin([...])"` (bracket-indexing style). Every
consumer in DecoupleRpy_Agent (`rna.py`, `microarray.py`, `activity_stats.py`,
`manifest_data_validation.py`) calls `obs_df.query(subset_query)`, which has no
`obs` name in its eval namespace → `NameError: name 'obs' is not defined`. This
silently broke the documented "use subset_query from default_contrasts"
workflow for the Bailey (Squamous vs Pancreatic Progenitor) and Puleo
(PureBasal-like vs PureClassical) default contrasts — the most likely
subtype contrasts to be requested for these datasets.

**Fix**: rewrote to `.query()`-compatible syntax:
- `paca_au_rnaseq.yaml`, `paca_au_array.yaml`:
  `` "`membership.ordered`.isin(['Squamous', 'Pancreatic Progenitor'])" ``
  (backticks required — column name contains a `.`)
- `puleo_2018.yaml`: `"WholeTumorClass.isin(['PureBasal-like', 'PureClassical'])"`

**Secondary fix (`paca_au_rnaseq.yaml`)**: `Sample.type` declared
`allowed_values: ["Primary tumour", "Cell line"]`, but real data has
`"Cell line "` (trailing space, 8 samples) and `"Metastatic tumour"` (2
samples, not declared at all). Updated `allowed_values` to
`["Primary tumour", "Cell line ", "Metastatic tumour"]` and rewrote the
interpretation_warning with the real composition (80 primary / 8 cell line /
2 metastatic / 2 unrecorded, out of 92).

**Result after fixes**: all three manifests validate clean
(`overall_valid: True`, 0 errors). `puleo_2018` retains one *expected*
warning — `data_level` can't be auto-classified from value range (0.32–73.9)
because of its documented non-standard normalization; this is already called
out in the manifest ("do not back-transform") and is not a new issue (see
"Puleo 2018 data_level" note below).

**Puleo 2018 data_level / back-transform implications**: the non-standard
0.32–73.9 range means generic "is this log2 data" heuristics can't confirm
the declared `log_expression` data_level — hence the warning. This does NOT
cause errors in the actual analysis path: limma/t-test (Path B) operate
directly on whatever values are in `.X` without assuming a specific log base,
and the manifest's "do not back-transform or re-normalize" rule prevents any
tool from applying a `2**x`/`expm1`-style correction that would be wrong for
this non-standard scale. The only risk is in *interpretation* — e.g. reporting
"fold change of 2^logFC" language would be misleading for this dataset, since
the underlying transform isn't a clean log2. No code currently does this
back-transform for any dataset, so there's no active bug — just an
interpretation caveat already covered by existing reporting_rules.

---

## What Was Done (2026-06-12)

### Precompute Cache Phase 1 + HF host migration (anni-voigt → anne-voigt)

**11 pre-existing `expression_source.type: url` manifests**: `url` (and any
`note` text referencing the host) migrated from `anni-voigt/pdac-research-data`
→ `anne-voigt/pdac-research-data` (`cptac_pda`, `gse15471_badea`,
`gse17891_collisson`, `gse21501_stratford`, `gse50827_nones`, `gse57495`,
`paca_au_array`, `paca_au_rnaseq`, `paca_ca_rnaseq`, `puleo_2018`,
`tcga_paad`). The `anni-voigt` → `anne-voigt` HF account transfer (separately
pending since before 2026-06-09) is now complete.

**5 remaining `geo_series_matrix` manifests precomputed to `url`/h5ad**,
bringing all 16 to load-path parity (single `decoupler_load_url_counts` step
instead of a 5-6 step live `geo_series_matrix` pipeline):

| Dataset | Shape | GPL annotation added |
|---|---|---|
| `gse71729_moffitt` | 357 × 19,749 | none — gene symbols already in var.index |
| `gse71989_chen` | 22 × 54,675 | GPL570, 83.7% gene-symbol coverage |
| `gse62165_jiang` | 131 × 49,386 | GPL13667, 100% coverage |
| `gse16515_mayo` | 52 × 54,613 | GPL570, 83.8% coverage; **linear scale preserved** (data_level: normalized, no log2 applied) |
| `gse28735_pdac` | 90 × 28,869 | GPL6244, 87.6% coverage via new `gene_assignment`-column parser (GPL6244 has no native "Gene Symbol" column) |

For `gse28735_pdac`, `feature_mapping.gene_symbol_column` changed from
`"Gene Symbol"` → `"gene_symbol"` to match the precomputed
`var["gene_symbol"]` (derived from `gene_assignment`'s first `///`-group's
2nd `//`-field). `feature_id_type: entrez_id` is unchanged — `var.index`
remains 7-digit numeric GPL6244 probe IDs.

Each of the 5 manifests retains a new `original_source: {type:
geo_series_matrix, url: ...}` block for provenance and rebuild via
`DecoupleRpy_Agent/scripts/assemble_<dataset_id>.py` + the shared
`scripts/_precompute_common.py` helpers (new: `_ensure_gse_family_soft`,
`annotate_with_gpl`, `annotate_with_gpl_gene_assignment`, `stamp_provenance`,
`write_and_upload`).

All 16 manifests re-verified via `dataset_describe` (loading_plan step 1 =
`decoupler_load_url_counts`, `validation.valid == True`) and
`dataset_validate_manifest_against_data` (`overall_valid == True`, 0 errors;
`gse16515_mayo` carries 1 pre-existing warning — `data_level: normalized`
can't be auto-classified from value range alone, same as before precompute).

Committed as `1074739` ("Precompute cache for 5 GEO datasets + migrate HF
host anni-voigt -> anne-voigt"), pushed to `origin`. DecoupleRpy_Agent's
`requirements.txt` bumped to pin this commit (+ added explicit
`GEOparse==2.0.4`, previously an unpinned transitive dependency).

### Side effect
DecoupleRpy_Agent's `src/cache.py:preload_datasets()` no longer preloads
these 5 at server startup (previously preloaded all `geo_series_matrix`-type
datasets) — faster cold start. Probe→gene collapse remains a per-query step
for all probe-indexed datasets across all 16 (Phase 2, not started).

---

## Validated Manifest Status

**All 16 manifests now use `expression_source.type: url` / format `h5ad`**
(parity achieved 2026-06-12 — see "What Was Done (2026-06-12)" above). The
tables below describe platform/feature/survival characteristics, which are
unchanged by the precompute migration.

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

### Chan-Seng-Yue 2020 (COMPASS) — INVESTIGATED 2026-06-14, confirmed blocked
- Open supplement checked directly (springer static-content ESM, article HTML is
  IDP-auth-gated): MOESM3 xlsx = 7 tables, none per-sample; MOESM1 22MB SI PDF has
  247 `PCSI_####` ids but only as heatmap/figure labels, no machine-readable
  subtype-per-sample table. Subtype terms appear only in prose/aggregate counts.
- ID crosswalk WOULD work: 157/234 of paca_ca's `submitted_donor_id.x` PCSI donors
  appear in the paper (rest are a separate `MPCC_*` cohort); join must be
  donor-level (specimen suffixes differ: `PCSI_0279_Pa_P` vs `PCSI_0132_Pa_P_526`).
- Blocked because labels aren't openly tabulated, NOT because of ID mismatch. Only
  routes: EGA DAA for annotated processed data, or figure-bar digitization
  (unreliable). Not worth pursuing for the demo.
- Recorded a precise sourced limitation in `paca_ca_rnaseq.yaml`. See
  REGISTRY_TODO_PLANS.md §4.4-D.

---

## What Was Done (2026-06-09)

### 8 datasets attempted, 7 successfully added
- Wrote Python assembly scripts for each dataset (in DecoupleRpy_Agent/scripts/)
- Installed GEOparse into DecoupleRpy_Agent .venv
- Downloaded 3 pdacR RDS files directly from GitHub (no R package install possible)
- Installed pyreadr (didn't work for pdacR lists) + data.table R package for fast CSV export
- Installed cptac Python package for CPTAC-PDA
- All h5ad files uploaded to `anni-voigt/pdac-research-data` (now migrated to
  `anne-voigt/pdac-research-data`, see 2026-06-12 section above)
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
- GEOparse's own FTP download of `{GSE}_family.soft.gz` is unreliable for files
  >~20MB — pre-fetch over HTTPS via `requests` first (see
  `DecoupleRpy_Agent/scripts/_precompute_common.py::_ensure_gse_family_soft`,
  added 2026-06-12), then point `GEOparse.get_GEO()` at the local file.

---

## Known Issues / TODOs

### 1. pdacR install broken on this machine — LOW PRIORITY
illuminaHumanv4.db and hgu219.db fail to install via BiocManager on Bioc 3.22 / R 4.5.3.
Workaround (individual .rds downloads) works fine for data extraction.

### 2. No HF deployment for biodata-registry — LOW PRIORITY
Not currently needed since DecoupleRpy_Agent imports directly.

### 3. Tests only cover schema validation — ADDRESSED 2026-06-14
Added `tests/test_manifests_against_data.py` — opt-in (`RUN_LIVE_DATA_TESTS=1`,
`live` marker), parametrized over all 16 manifests. Downloads + caches each h5ad
and asserts: declared metadata columns exist (embedded metadata only),
`allowed_values` cover real obs values (numeric-aware so 0/0.0/"0"/"1.0" match;
literal `nan`/trailing-space preserved), `feature_id_type` vs `var.index`,
`raw_counts` non-negative + integral, every `default_sample_filter` /
`subset_query` / survival column evaluates, and `curated_sample_list` barcodes are
present. 16/16 live + 19/19 offline pass. Caught + fixed two real
`missing_values` gaps (`paca_au_rnaseq.Sample.type`, `puleo_2018.Resection.margin`).
Run with the DecoupleRpy_Agent venv (has anndata/scipy):
`RUN_LIVE_DATA_TESTS=1 PYTHONPATH=. /path/to/DecoupleRpy_Agent/.venv/bin/python -m pytest -m live`.

**Pre-existing schema bug surfaced (not yet fixed):** `gse50827_nones` has
`group_columns: []` → fails `DatasetManifest.validate()`. Survival-only dataset
with no DE grouping column; fix is a design decision (relax schema vs. add a
group column). See REGISTRY_TODO_PLANS.md §4.4-E.

### 4. TCGA-PAAD sample curation — MEDIUM PRIORITY
18.9% non-PDAC contamination. Curated barcode list added to manifest (Knudsen 2019).

### 5. Collisson subtypes — DONE 2026-06-14 (Route 1, original labels)
Curated from Collisson 2011 Suppl Table 2 (`41591_2011_BFnm2344_MOESM20_ESM.xls`,
downloads openly from springer static-content even though the article is auth-gated).
Added `obs['collisson_subtype']` to both the main + collapsed h5ads (re-uploaded to
HF) and to the manifest: 46/47 labeled (classical 22 / QM 19 / exocrine-like 5),
Capan1 (GSM446778) unlabeled (absent from supplement). New QM-vs-classical
tumour-only default_contrast. Script:
`DecoupleRpy_Agent/scripts/annotate_gse17891_collisson_subtypes.py`. NB: same
supplement also has GSM-keyed subtypes for Badea/GSE15471 (future enhancement).

### 6. Chan-Seng-Yue 2020 COMPASS subtypes — BLOCKED (investigated 2026-06-14)
Open supplement has no machine-readable per-sample subtype table (only figure
labels + aggregate counts). Donor-ID crosswalk to paca_ca is feasible (157/234)
but no label values to join. Needs EGA DAA. See COMPASS section above + §4.4-D.

### 7. gse50827_nones Excel-corrupted gene symbols — LOW PRIORITY
Some gene names are date artifacts (e.g., '1-Dec', '1-Mar'). Documented in manifest limitations.
Fix requires re-mapping through Ensembl or original GPL10558 annotation.

### 8. Live GPL-annotation fallback (DecoupleRpy_Agent) broken for ad-hoc datasets — cross-reference
Not a biodata-registry issue directly — all 16 registered manifests are now
precomputed/pre-annotated (see 2026-06-12 section above). But
`decoupler_annotate_probes_with_gpl` in DecoupleRpy_Agent's
`src/workflows/geo.py` — the live, agent-facing path for *unregistered* GEO
datasets — is broken for GPL570 (404 on platform-level SOFT/annot files) and
GPL13667 (6GB family SOFT file). If a 17th manifest on one of these platforms
is ever added without precomputing first, this will resurface. See
`DecoupleRpy_Agent/memory.md` Known Gaps #14.

---

## Git State

| Remote | URL |
|--------|-----|
| `origin` | `github.com/avoigt1121/biodata-registry` |

Branch: `main`. Up to date with origin (last push: `1074739`, 2026-06-12).
16 manifests registered; all 16 now `expression_source.type: url` (format `h5ad`).
