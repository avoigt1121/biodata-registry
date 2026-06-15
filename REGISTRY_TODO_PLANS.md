# biodata-registry — Implementation Plans for Open Items (§4.4 / §4.5)

Owner: registry maintainer. Created 2026-06-14.
Scope: the "In progress / to do" (§4.4) and "Per-dataset data-quality flags"
(§4.5) bullets from *PDAC System Status Reference* (13 June 2026), biodata-registry
section.

**Status snapshot of current HEAD (`133e55d`, 2 commits ahead of origin):** all 16
manifests parse and validate (0 errors, 1 known `gse16515_mayo` warning). Every
§4.5 data-quality flag is already *encoded* in its manifest (refusal rules,
`default_sample_filter`, interpretation warnings). What is missing across both
sections is the same thing: **automated verification of declared semantics against
the live h5ad data.** That single test harness (§4.4-E below) is the highest-leverage
item because it discharges most of §4.5 at once.

---

## §4.4 — In progress / to do

### A. Collisson subtype labels for `gse17891_collisson` — MEDIUM

**Goal.** Add per-sample Collisson 2011 subtype labels (quasi-mesenchymal / QM,
exocrine-like, classical) to the 27 tumor-tissue samples of GSE17891 so that
subtype-stratified contrasts become answerable. Cell-line filtering is already
solved (`default_sample_filter: tissue == 'ductal adenocarcinoma tumor'`), so this
item is purely the labels.

**Why it's not trivial.** The labels were never deposited in GEO
(`metadata_source` confirms this). They live in Collisson et al. 2011, *Nature
Medicine* 17:500–503, Supplementary Table S1. The hard part is mapping the paper's
sample identifiers to GEO **GSM** accession IDs (the h5ad `obs.index`).

**Two routes — pursue Route 1 first, fall back to Route 2.**

*Route 1 — manual curation from Table S1 (preferred, authoritative).*
1. Obtain Supplementary Table S1 from the paper (publisher supplement / PMC
   `PMC3146339`). Extract the sample → subtype table (27 microdissected tumors).
2. Build the GSM crosswalk. Pull the GSE17891 series matrix sample titles
   (already embedded in the h5ad `obs`; also on the GEO series page). Match paper
   sample names ↔ GSM titles. Expect some manual disambiguation; record every
   mapping decision in a provenance comment.
3. Encode as a new metadata column. Add to the h5ad assembly script
   (`DecoupleRpy_Agent/scripts/assemble_gse17891_collisson.py`) a
   `collisson_subtype` obs column (values: `QM`, `exocrine-like`, `classical`,
   plus `""`/NA for the 20 cell lines), re-upload the h5ad, and bump the manifest
   to point at the new file.
4. Manifest edits:
   - Add `collisson_subtype` to `metadata_columns` with
     `role: subtype`, `biological_grouping_allowed: true`,
     `allowed_values: [QM, exocrine-like, classical]`,
     `missing_values: [""]`, and an interpretation warning noting cell lines are
     unlabeled.
   - Add `default_contrasts` (e.g. `QM` vs `classical`, `subset_query:
     "collisson_subtype.isin(['QM','classical'])"`, `method: limma`).
   - Remove the "subtype labels are not in this h5ad" refusal rule and the
     matching `limitations` bullet; replace with a citation line (Collisson 2011
     Table S1) and the curation provenance.

*Route 2 — computational reclassification (fallback if S1↔GSM mapping is
unrecoverable).* Apply Collisson's own **PDAssigner** 62-gene nearest-centroid
classifier to the 27 tumor samples. The gene list and centroids are published in
the same paper. This regenerates labels without needing the per-sample table, but
results are *derived*, not the original calls — so mark the column
`subtype_source: PDAssigner_recomputed` and state that in reporting_rules. Use
only if Route 1 fails.

**Acceptance criteria.** 27 tumor samples carry non-null subtypes; cell lines are
NA; `dataset_validate_manifest_against_data` passes; the live-data test (§4.4-E)
confirms `allowed_values` cover the real obs values; a subtype contrast runs
end-to-end.

**Effort.** ~0.5 day if S1 is clean and titles map 1:1; up to 1 day with
disambiguation. Route 2 is ~0.5 day.

---

### B. TCGA-PAAD curated PDAC-only barcode list — ✅ DONE (verified 2026-06-14)

This item is **complete in biodata-registry**; no further action here.

Verification performed against [`tcga_paad.yaml`](biodata_registry/manifests/tcga_paad.yaml):
- `curated_sample_list` present with **150 barcodes** (`grep -c` confirmed),
  sourced from Knudsen et al. 2019 (PMC6357157), Table S1
  (`curated_sample_source` records the citation + GitHub provenance
  `cit-bioinfo/TCGA_PAAD_survival`).
- Schema supports it: `manifest_schema.py:267-268` define
  `curated_sample_list` / `curated_sample_source`, round-tripped in `from_dict`
  and `to_dict`.
- Guardrails wired: `refusal_rules` require `dataset_filter_to_curated_samples`
  before any survival/prognostic analysis; `dataset_disclaimer` and
  `limitations` state the curated subset is applied automatically by the loading
  plan.

**Remaining (cross-repo, NOT a registry task).** The §3.5 DecoupleRpy item — having
`dataset_filter_to_curated_samples` actually consume `curated_sample_list` and
auto-apply it for survival workflows — lives in DecoupleRpy_Agent. The registry
contribution (the list + schema + rules) is finished. Recommended follow-up:
confirm in DecoupleRpy_Agent that the tool reads `curated_sample_list` from the
manifest (not a hardcoded copy).

---

### C. `gse50827_nones` Excel-corrupted gene symbols — LOW

**Goal.** Repair gene symbols mangled into date artifacts by Excel autoformat
(e.g. `1-Dec`, `1-Mar`, `1-Sep`) so feature lookups for those genes succeed.
Currently documented only as a warning in `limitations` + `reporting_rules`.

**Critical caveat — do not guess from the corrupted string.** Date artifacts are
*ambiguous*: `1-Mar` could mean `MARCH1`/`MARCHF1` **or** `MARC1`; `1-Dec` could
mean `DEC1`/`DELEC1` **or** `BHLHE40`. A regex-only "un-corrupt" mapping will
silently assign wrong genes. The only robust fix re-derives symbols from
unambiguous probe IDs.

**Plan (preferred — re-derive from probe annotation).**
1. Re-assemble from the original probe-level source. The current h5ad is already
   mean-collapsed to (corrupted) symbols by pdacR, so the probe→symbol step must
   be redone from the GPL10558 annotation, not from the collapsed file. Source
   options, in order: (a) pdacR `Nones_GEO_array.rds` if it retains probe IDs;
   (b) the GEO **GSE50827** series matrix (probe-level) + the **GPL10558**
   platform annotation table (Illumina probe ID → official symbol); (c) the
   `illuminaHumanv4.db` Bioconductor annotation (note: install is broken on this
   machine per memory.md — use the flat GPL10558 SOFT table instead).
2. Map probe IDs → current HGNC symbols using the platform annotation (these IDs
   are never date-corrupted), then mean-collapse. This reproduces the assembly
   cleanly.
3. Re-upload the corrected h5ad; manifest `expression_source.url` stays the same
   filename (overwrite) or bumps with a `note` recording the re-map.
4. Update `limitations`/`reporting_rules`: replace the Excel-corruption warning
   with a line stating symbols were re-derived from GPL10558 probe annotation.

**Cheap stop-gap (only if re-assembly is deferred).** Add a small curated
remap dict for the *unambiguous* subset of known Excel gene corruptions and apply
it at assembly, leaving genuinely ambiguous ones flagged. Document that this is
partial. Do **not** ship this as the final fix.

**Acceptance criteria.** No `var.index` entries match the date-artifact regex
`^\d{1,2}-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$`; spot-check that
SEPT/MARCH/DEC-family genes resolve to a single defensible symbol; validation
passes.

**Effort.** ~0.5–1 day, gated on locating a probe-level source for GSE50827.

---

### D. Chan-Seng-Yue 2020 (COMPASS) subtypes — INVESTIGATED 2026-06-14: confirmed blocked

**Outcome of the open-supplement check (Route 1).** The "labels may be obtainable
without EGA" hypothesis was tested and **does not hold** — but for a sharper
reason than originally assumed:

- The open supplement was retrieved directly from springer static-content
  (article HTML is behind an IDP auth redirect; the ESM files are not):
  `41588_2019_566_MOESM3_ESM.xlsx` (7 supplementary tables) and the 22 MB
  `MOESM1_ESM.pdf` (Supplementary Information).
- **None of the 7 xlsx tables is a per-sample subtype table.** They are cohort
  summary, SMAD4 loss, Fig-2b marker genes, NMF gene lists, GO pathways, mutation
  networks, and a basal/classical genomic-explanation summary (aggregate counts
  like "40/42 cases").
- The SI PDF mentions 247 unique `PCSI_####` IDs, but only as **heatmap/figure
  column labels** (adjacent to gene-name row labels), never in a machine-readable
  row with a subtype value. Subtype terms (basal-like-A/B, classical-A/B, hybrid)
  appear only in prose.
- **The ID crosswalk itself is feasible**: 157/234 of this cohort's `submitted_donor_id`
  PCSI donors appear in the paper (the remaining ~77 are a separate `MPCC_*`
  cohort). So if per-sample labels were ever obtained, joining them to
  `paca_ca_rnaseq` by donor ID would work for ~67% of donors. Specimen-level IDs
  do not match (paca_ca `PCSI_0279_Pa_P` vs SI `PCSI_0132_Pa_P_526`), so any
  future join must be donor-level.

**Verdict.** Genuinely blocked — not by anonymized IDs, but because the labels are
not openly tabulated. The only routes are (a) EGA controlled-access to the
annotated processed data (needs a Data Access Agreement; not worth it for a demo),
or (b) digitizing figure color-annotation bars (not defensible as ground truth).
Action taken: recorded a precise, sourced limitation in `paca_ca_rnaseq.yaml`
(donor crosswalk feasible, labels unavailable, "do not claim COMPASS subtypes").
No further work unless a DAA is pursued.

Original plan retained below for reference.

---

### D-orig. Chan-Seng-Yue 2020 (COMPASS) subtypes — LOW (mostly blocked)

**Status.** Raw COMPASS expression is EGA controlled-access (ICGC PACA-CA
pathway) and not pursuable without a Data Access Agreement. PACA-CA *expression*
is already in the registry as `paca_ca_rnaseq`; only the **subtype labels** are
missing.

**Key insight — the labels may be obtainable without EGA access.** We do not need
the controlled raw data to *label* `paca_ca_rnaseq`; we need a per-specimen
subtype table. Chan-Seng-Yue et al. 2020, *Nature Genetics* 52:231–240, ships
supplementary tables that may include per-sample Moffitt/basal-classical and
COMPASS subtype calls keyed to ICGC specimen IDs.

**Plan.**
1. *Try the open path first.* Download the paper's supplementary tables. Look for
   a sample table with specimen/donor identifiers + subtype assignments. If those
   identifiers are ICGC `SP...`/`DO...` IDs, they can be matched directly to
   `paca_ca_rnaseq` `obs.index` (specimen IDs, `SP...` format) — no EGA needed.
2. If matched: add a `compass_subtype` (and/or `moffitt_subtype`) column at
   `paca_ca_rnaseq` assembly, encode in `metadata_columns` with allowed_values +
   provenance, add subtype `default_contrasts`, and relax the "no subtype labels"
   limitation. This converts paca_ca from an unlabeled cohort into a Bailey/Puleo
   peer.
3. *If the supplement only has internal/anonymized IDs* that can't be crosswalked
   to ICGC specimen IDs → genuinely blocked. Document the blocker, file the DAA
   pathway as the only route, and leave the limitation as-is. Do not pursue
   controlled data for a demo.

**Acceptance criteria (conditional on step 1 succeeding).** ≥ majority of
`paca_ca_rnaseq` primary-tumour specimens carry a subtype; validation passes;
provenance cites Chan-Seng-Yue 2020 supplement.

**Effort.** ~0.5 day to check the supplement and attempt the crosswalk; abandon
if IDs don't match.

---

### E. Tests verify only schema, not live-data column values + no HF deployment — ✅ DONE (2026-06-14)

This is the **keystone item** — it also discharges most of §4.5.

**Implemented.** [`tests/test_manifests_against_data.py`](tests/test_manifests_against_data.py)
— opt-in (`RUN_LIVE_DATA_TESTS=1`), `live` marker, parametrized over all 16
manifests, downloads + caches each h5ad and asserts the checks below. Added a
`test` optional-dependency extra and registered the `live` marker in
`pyproject.toml`. Result: **16/16 live + 19/19 offline pass.**

Two real manifest gaps were caught and fixed in the process:
- `paca_au_rnaseq.yaml` `Sample.type`: added `missing_values: [""]` (2 unrecorded
  samples stored as empty string, previously undeclared).
- `puleo_2018.yaml` `Resection.margin`: added `missing_values: [""]`.

Pre-existing issue surfaced (NOT introduced here, out of this change's scope):
`gse50827_nones` has `group_columns: []`, which fails `DatasetManifest.validate()`
("group_columns must have at least one entry"). The old offline suite never
caught it (it only validated the Moffitt manifest). It is survival-only with no
DE grouping column — fix is a design choice (relax the schema rule for
survival-only datasets vs. add a grouping column). Flagged for a decision.

Original plan retained below for reference.

---



**Goal.** Add an opt-in test module that downloads each manifest's h5ad (cached)
and asserts the manifest's declared semantics hold against the real data.

**Plan.**
1. New file `tests/test_manifests_against_data.py`, guarded by a pytest marker
   (`@pytest.mark.live`) and skipped unless `RUN_LIVE_DATA_TESTS=1` (keeps the
   default `pytest tests/` fast and network-free). Cache downloaded h5ads under a
   tmp/XDG cache dir so reruns are cheap.
2. Parametrize over all 16 manifests. For each, load the h5ad and assert:
   - every key in `metadata_columns` exists in `adata.obs`;
   - for columns with `allowed_values`, the set of real obs values ⊆
     `allowed_values ∪ missing_values` (this is exactly the check that caught the
     `paca_au_rnaseq` `"Cell line "` trailing-space / `"Metastatic tumour"` bug —
     see memory.md 2026-06-14);
   - `feature_id_type` is consistent with `var.index` (e.g. probe-like vs symbol);
   - `data_level` range sanity (counts are non-negative integers for
     `raw_counts`; log ranges for `log_expression`) — tolerate the documented
     `gse16515_mayo` / `puleo_2018` exceptions via an allowlist;
   - **every `default_sample_filter`, `default_contrasts[].subset_query`, and
     survival column reference evaluates without error** via `adata.obs.eval` /
     `adata.obs.query` (this is the generalized guard against the
     `obs['col'].isin(...)` syntax bug fixed on 2026-06-14);
   - declared `curated_sample_list` barcodes (TCGA) are a subset of available
     samples.
3. Wire into CI as a separate, optional job (manual / nightly), since it needs
   network + HF bandwidth. Keep it out of the fast unit lane.

**No HF deployment.** Confirmed not needed — biodata-registry is consumed as a
pinned pip dependency (`git+https://...@<commit>`), not over MCP, by
DecoupleRpy_Agent. No action; documented here to close the bullet. (The optional
FastMCP `server.py` remains available for local use; deploying it as a hosted
Space is explicitly out of scope.)

**Acceptance criteria.** `RUN_LIVE_DATA_TESTS=1 pytest -m live` passes for all 16
manifests; the suite re-detects the two historical bugs if reintroduced.

**Effort.** ~1 day for the parametrized harness; this is the recommended next
build because it also validates §4.5 below.

---

## §4.5 — Per-dataset data-quality flags

**All five flags are already encoded** in their manifests (verified 2026-06-14).
There is no net-new authoring work; the plan for this section is **verification +
light hardening**, almost entirely covered by the §4.4-E live-data test harness.
Per-dataset status and the specific assertion that locks each flag:

| Dataset | Flag | Current encoding (verified) | Hardening / verification step |
|---|---|---|---|
| `gse15471_badea` | "normal" = adjacent tissue, not healthy | `sample.interpretation_warning` + 2 refusal rules forbidding "healthy pancreas/baseline" framing; reporting_rules restate it | §4.4-E asserts `sample ∈ {tumor, normal}`. No further encoding needed. Optional: an interpretation-language lint at the agent layer (DecoupleRpy), not the registry. |
| `gse21501_stratford` | survival not in GEO; two-color log-ratio, negatives valid | refusal_rules block survival; data_level + value-range note cover negative log-ratios | §4.4-E asserts no survival columns are declared and value range spans negatives as documented. |
| `gse17891_collisson` | 20/47 are cell lines — filter first | `default_sample_filter: tissue == 'ductal adenocarcinoma tumor'` + refusal rule against cell-line-inclusive tumor DE | Already enforced. §4.4-E asserts the filter evals and yields 27 samples. (Subtype *labels* are the separate §4.4-A item.) |
| `paca_ca_rnaseq` | mixed primary/cell-line/met/PDX; survivalB sub-threshold | `default_sample_filter` to primary tumour + refusal rule against mixing specimen types; survivalB intentionally not encoded | Already enforced. §4.4-E asserts `default_sample_filter` evals and the survival columns point only at the ≥80%-coverage endpoint. |
| `cptac_pda` | RSEM TPM not cross-comparable w/o batch correction; 131/193 matched clinical | refusal_rule against direct TPM comparison to GEO/TCGA; limitations note clinical-match count | Already enforced. §4.4-E asserts clinical-derived columns exist for the documented subset; cross-cohort comparison guard is an agent-layer concern. |

**Recommendation.** Do not open per-dataset work for §4.5. Instead, fold each row's
"verification step" into the §4.4-E parametrized harness as explicit assertions so
the flags can't silently regress (the exact failure mode that produced the
`paca_au_rnaseq` `allowed_values` bug). Anything in the right-hand column marked
"agent-layer" (interpretation-language hedging, cross-cohort comparison blocking)
is enforced in DecoupleRpy_Agent's reporting guardrails, not in this repo.

---

## Suggested execution order

1. **§4.4-E live-data test harness** — keystone; also locks all of §4.5. (~1 day)
2. **§4.4-A Collisson subtypes** — highest user-facing value (unlocks a real
   subtype analysis). (~0.5–1 day)
3. **§4.4-D COMPASS supplement check** — cheap to attempt, high upside if the
   labels crosswalk to ICGC specimen IDs without EGA. (~0.5 day)
4. **§4.4-C Nones symbol re-map** — gated on finding a probe-level source. (~0.5–1 day)
5. **§4.4-B TCGA curated list** — ✅ done; only the DecoupleRpy-side consumption
   check remains (cross-repo).
