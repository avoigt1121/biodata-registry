# memory.md — biodata-registry Working State

Last updated: 2026-06-29

---

## 2026-06-29 — 0.1.7 released: single-cell readiness (Loveless TODO, Phases 2–3 registry-side)

Registry-side groundwork for the **Loveless single-cell dataset** ingestion
(TODO §"Dataset ingestion"). The manifest itself stays blocked on Phase 1 (the
offline 33.4 GB `.rds`→h5ad conversion on a high-RAM HF Job); only the
schema/engine gaps that need no data were closed here.

- **`manifest_schema.py`** (`f658367`): `VALID_WORKFLOWS` gains `sc_annotation` +
  `pseudobulk_de`. `analysis_path` now checks **modality before data_level** —
  `sc_rnaseq`/`spatial_rnaseq` → `"P"` (pseudobulk/annotation) regardless of
  `data_level`, so an sc raw-counts h5ad is never mislabeled Path A (the
  DESeq2-on-cells pseudoreplication trap). New `_SINGLE_CELL_MODALITIES`. **Note:
  `analysis_path` now has THREE values (A/B/P)** — consumers that branch on it
  must handle "P".
- **`integration.py`** (`f658367`): new **Gate 4b `CROSS_RESOLUTION`** between the
  modality (4) and data_level (5) gates. `bulk` + `sc_rnaseq`/`spatial_rnaseq`
  refuses instead of early-pooling cells×genes with samples×genes (both are
  "transcriptome", so Gate 4 passes them and equal raw_counts would early-pool).
  Mirrors the proteome gate; same-resolution sc+sc still proceeds. New
  `SINGLE_CELL_MODALITIES` + `CROSS_RESOLUTION` constant.
- Tests: 64 passed, 2 skipped (fastmcp not installed). Source pushed to `github`.
- **Release/re-pin:** `hf upload` to `anne-voigt/biodata-registry` worked this
  session (logged in as `anne-voigt`, write access) → wheel
  `biodata_registry-0.1.7-py3-none-any.whl`, HF rev
  `eef040633cebade84c513b7467b9dad0c9a8625f`,
  sha256 `3056ec41edb234c5bbc6a9d0156f747001445c977df8260f48b56d3563822f93`.
  (Contrast the older note below that the upload 403'd — today's session had a
  write-scoped login.)
- **Agent re-pin DEPLOYED to DEV** (not prod). The 0.1.7 pin was committed to the
  agent's `main` (commit `45ace9a`, requirements.in + .txt only) in an isolated
  worktree — deliberately NOT on the `feat/loveless-sc-serving` branch, which has
  unrelated agent-side single-cell-serving WIP (ADR-0006 + signatures.py +
  rna_sc.py, concurrently committed by the user as `6e9f020`). Pushed to the dev
  Space (`hf-dev/main` `c1cece4`→`45ace9a`). **Prod (`origin/main`) deliberately
  NOT pushed** — gated on dev validation. ⚠ A wheel re-pin needs a **FACTORY
  rebuild** of the Space (a normal rebuild serves the stale cached install — the
  0.1.6 lesson below); the factory rebuild is a Space-Settings UI action (can't be
  done from CLI) and dev RUNNING can't be verified from here (private Space). So:
  user factory-rebuilds dev → confirms RUNNING → then promote `main` to prod
  (`git push origin main`) + factory-rebuild prod. Note 0.1.7 is **inert** for the
  agent until a single-cell manifest ships (none registered yet), so no functional
  change for end users yet.
- **Phase 1 conversion tooling READY** (`46b955a` + `47b1546`):
  `scripts/ingest/loveless/` (`convert_rds_to_h5ad.R` + `assemble_h5ad.py` +
  `subset_h5ad.py` + `run_job.sh` + `Dockerfile` + `README.md`) — the launch-ready `.rds`→h5ad
  pipeline (schema report → raw-counts extraction → gzip h5ad → upload to private
  `pdac-research-data`). Two-pass: discover the real cohort/sample columns (Pass 1)
  then emit the Steele subset (Pass 2). **Confirmed launch params** (`hf jobs
  hardware` / `--help`, 2026-06): flavor **`cpu-performance`** (32 vCPU/256 GB/
  1024 GB disk/$1.90/hr; `cpu-xl` 124 GB fallback), image baked `FROM
  satijalab/seurat:5.5.1`, `hf jobs run --detach --flavor cpu-performance
  --secrets HF_TOKEN --env SUBSET_COL/SUBSET_VALUE`. `hf jobs run` needs a
  pre-built image (no local mount) → build+push the Dockerfile first. **Two-mode
  driver** (`ccb6b09`): Pass 1 = full convert on `cpu-performance` (~$4–9); Pass 2
  branches on `SUBSET_COL` to a **subset-only** path (`subset_h5ad.py`, backed
  read) that pulls Pass 1's full h5ad and filters — no Zenodo/R re-run, ~15–30 min
  on `cpu-xl` (<$1). **All-in run cost ~$10–15.** STILL TO RUN (not CLI-runnable).
  Once run, the manifest unblocks → 0.1.8 + re-pin.

---

## 2026-06-24 (later) — ADR-0001 decision-matrix doc added + concordance VALIDATED live on dev

- **Authoritative `docs/adr/ADR-0001-decision-matrix.md` added** (`5381756`) — the engine's
  spec now lives beside `integration.py`. It had only existed as a stale Phase-0 copy in
  `DecoupleRpy_Agent/docs/adr/`, which was reduced to a pointer (agent `0ac9103`). Matched
  to 0.1.6: same-cohort/concordance gate, `DUPLICATE_COHORT`, hardened Gate 6, worked
  examples, refusal taxonomy.
- **0.1.6 concordance gate VALIDATED end-to-end on the live dev agent.** A
  `gse205154_sears` + `gse205154_sears_tmm` request → `get_integration_plan` returns
  `mode="concordance"` (with `cohort_id`/`variant` in `per_dataset`); the agent routes to
  `decoupler_normalization_concordance`, not meta-analysis.
- **⚠ Operational lesson: re-pinning the wheel needs a FACTORY rebuild of the consuming
  Space**, not a normal one — the dev Space served a *stale pre-0.1.6* `biodata_registry`
  (pip/build cache) despite the correct pin; a factory rebuild installed 0.1.6. Applies to
  the pending prod promotion.

---

## 2026-06-24 — storage posture: private-by-default (ADR-0005)

Recording the ADR-0005 decision (lives in `DecoupleRpy_Agent/docs/adr/ADR-0005-private-storage-persistence.md`) on the registry side, since the manifests point at the h5ad host it governs. Docs-only — no manifest/schema/loader change.

- **`anne-voigt/pdac-research-data` stays PRIVATE by default** (confirmed private 2026-06-24). PRO's 1 TB private tier removes the free-tier pressure that drove public-by-default; "public" is now a deliberate, publication-time choice per dataset, not a storage workaround.
- **Don't prune h5ads to save space.** Keep one canonical variant per cohort and retain siblings (e.g. the GSE205154 `gse205154_sears` TPM / `_counts` / `_tmm` trio) rather than dropping them — storage caps no longer force it.
- **Data Studio (private Dataset Viewer) = first-pass check** in the `validate_manifest_against_data` workflow: eyeball a manifest's file in-browser before/after the programmatic validation, instead of download-and-open.
- **Onboarding convention:** new datasets land private; "promote to public" is a publication-time checklist step.

The lit-agent corpus half of ADR-0005 (retain snapshots, don't minimize) belongs in lit-agent's own CLAUDE.md (separate repo). SHOWCASE_STATUS.md carries the cross-repo h5ad-hosting line.

## 2026-06-24 session — 0.1.6 released (same-cohort gate: `cohort_id`/`variant` + `concordance`)

Built + shipped the **0.1.6** wheel (the same-cohort source work from the
2026-06-22 session below) and re-pinned the consumer. Same git-push publish path
as 0.1.1–0.1.5 (the read-only HF API token 403s on `huggingface-cli upload`, so
the wheel is git-tracked at the repo root + `git push hf`).

- **Release commit `261db0e`** (the staged 0.1.6 source — integration/schema/
  registry/server + 3 GSE205154 manifests + tests + CLAUDE.md + the wheel;
  pyproject was already at 0.1.6). Pushed to **both** `github`
  (`920b371..261db0e`) and `hf` (`920b371..261db0e`). The one-line
  `integration.py` docstring fix (ADR reference path →
  `docs/adr/ADR-0001-decision-matrix.md`) rode along. memory/TODO docs follow in
  a separate commit (the b46392c → 920b371 pattern).
- **Wheel** `biodata_registry-0.1.6-py3-none-any.whl`, **sha256
  `c4a218783dc59cbb203fe064a7b32fafe43b091d2979676e9724370305218275`**, **89844
  bytes**, **19 manifests**. Built with `uv build --wheel`. The untracked DRAFT
  `cptac_pda_counts.yaml` (h5ad not hosted) was moved out of `manifests/` for the
  build so setuptools' `package-data` glob couldn't bundle it — verified the wheel
  has exactly 19 manifests and no `cptac_pda_counts`, then restored it.
- **Isolated verification:** `uv pip install` of the wheel into a clean venv →
  version 0.1.6, 19 datasets, the 3 GSE205154 carry `cohort_id=gse205154`;
  `get_integration_plan` returns `concordance` for a sibling pair (empty
  `refusal_rules_triggered`) and the full trio, `refuse` + `DUPLICATE_COHORT` for
  siblings-plus-independent, and a non-concordance mode for two independent
  datasets. Offline suite 56 pass / 2 skip.
- **Resolve URL verified HTTP 200** + byte size (89844) + sha256 match:
  `https://huggingface.co/anne-voigt/biodata-registry/resolve/261db0e994eb2b5a7f3e8a40ca8d269cc89bda9b/biodata_registry-0.1.6-py3-none-any.whl`
  `--hash=sha256:c4a218783dc59cbb203fe064a7b32fafe43b091d2979676e9724370305218275`
- **Consumer pin (DecoupleRpy_Agent):** re-pinned `requirements.in` +
  `requirements.txt` 0.1.5 → 0.1.6 (URL above). requirements.txt is plain
  `uv pip compile` output (no `--generate-hashes`), so only the commit-pinned URL
  changed — there is no `--hash` line in the file; the sha256 is recorded here /
  in the commit body. Agent commit `fb2091e` (**LOCAL — not pushed**); dry-run
  resolve confirmed the 0.1.5 → 0.1.6 upgrade with no errors.
- **DEPLOYED 2026-06-24:** agent re-pin `fb2091e` is on **dev** (`hf-dev`,
  RUNNING on 0.1.6 — confirmed by the user after a transient cold-start 500
  cleared) and **prod** (`origin`, `c9b0d3a..fb2091e`, rebuilding on 0.1.6).
  Deterministic A/B before the push: 0.1.5 routed the GSE205154 sibling pair to
  `late` (meta-analyzed = double-count bug); 0.1.6 routes it to `concordance`.
  The live end-to-end query on the private dev Space could NOT be driven from
  this session — the cached HF API token lacks access to that Space (git push
  works, the API 404s) — so routing was verified deterministically (0.1.5→late
  vs 0.1.6→concordance), via the agent's `dataset_get_integration_plan`
  pass-through, and by the user confirming dev RUNNING.
- **Draft follow-on:** `cptac_pda_counts.yaml` stays untracked WIP (a planned
  same-cohort sibling of `cptac_pda` — Moffitt-subtyped GDC STAR-Counts build). It
  has NO `cohort_id`/`variant` yet and its h5ad isn't hosted, so it was excluded
  from 0.1.6. Before it ships: assemble + upload the h5ad AND add
  `cohort_id: cptac_pda` / `variant: counts` to it (and `cohort_id: cptac_pda` /
  `variant: tpm` to `cptac_pda` itself) so the pair routes to `concordance`.

---

## 2026-06-22 session — same-cohort variants: `cohort_id`/`variant` + `concordance` gate (source; RELEASED 2026-06-24 as 0.1.6 — see section above)

Made the GSE205154 sibling relationship machine-readable so `get_integration_plan`
stops mis-routing same-cohort variants into a meta-analysis. Source + tests +
version bump done; **wheel NOT built/published and DecoupleRpy_Agent NOT re-pinned**
(deploy step deferred for explicit approval).

- **Schema (`manifest_schema.py`):** two new optional fields on `DatasetManifest` —
  `cohort_id: str = ""` and `variant: str = ""`. Wired through `from_dict`
  (`d.get(...) or ""`), `to_dict`, and the field-reference docstring. Back-compatible
  (a manifest with neither still validates; no new validate() errors/warnings).
- **`registry.list_available_datasets()`:** each entry now carries `cohort_id` +
  `variant` so the agent sees the sibling relationship without loading each manifest.
- **Integration engine (`integration.py`):** new **Gate 1b** (runs after arity,
  *before* the data_level gate). When ≥2 requested datasets share a `cohort_id`:
  all-one-cohort → `mode="concordance"` (compare variants descriptively, empty
  `refusal_rules_triggered`); siblings mixed with independent datasets (or >1
  duplicated cohort) → `refuse` with new code `DUPLICATE_COHORT`. New module
  constants `CONCORDANCE` + `DUPLICATE_COHORT`; `_per_dataset_entry` now includes
  `cohort_id`/`variant`. Module + tool docstrings updated; server.py tool docstring
  updated. Top-level plan key set is UNCHANGED (concordance reuses the 9 keys).
- **Manifests:** the GSE205154 trio annotated `cohort_id: gse205154` + `variant:
  tpm`/`counts`/`tmm`. No other manifest has a cohort_id, so all prior integration
  results are unchanged.
- **Why before Gate 5:** siblings differ only in quantification; a TPM+TMM request
  (`tpm` ≠ `normalized`) would otherwise fall through to `late` and be
  meta-analyzed — exactly the double-count (Stouffer ~√N inflation; Q/I²=0 by
  construction) we are preventing. This is the registry-side fix for the agent run
  that meta-analyzed TPM vs TMM.
- **Tests:** `tests/test_integration_plan.py` +8 (sibling pair → concordance incl.
  pre-empting `late`; full-contract on a concordance plan; real trio → concordance;
  real TPM+TMM → concordance; siblings + independent → DUPLICATE_COHORT; two
  duplicated cohorts → DUPLICATE_COHORT; distinct single cohort_ids → not
  concordance/early; no-cohort regression → late). `tests/test_registry.py` +3
  (cohort_id/variant round-trip; trio shares cohort_id w/ distinct variants;
  list_available_datasets exposes cohort_id). **Full offline suite: 56 passed, 2
  skipped** (fastmcp + live-data skips, unchanged). End-to-end smoke confirmed all
  four modes on real ids.
- **pyproject:** `0.1.5` → `0.1.6`.
- **RELEASED 2026-06-24 as 0.1.6** (wheel built + pushed github/hf, resolve URL
  verified, consumer re-pinned locally — see the 0.1.6 section above). Only the
  agent Space *deploy* remains, pending explicit user approval.
- **Unrelated note:** `biodata_registry/manifests/cptac_pda_counts.yaml` is present
  but **untracked in git** and not in any wheel — pre-existing WIP, not part of this
  change. (It does validate; the suite includes it.)

---

## 2026-06-22 session — 0.1.5 released (per-dataset `preprocessing` field — Item 3)

Added a new optional structured manifest field **`preprocessing: str`** (plain-language
provenance) and cut **0.1.5**. Same git-push publish path as 0.1.1–0.1.4.

- **Schema** (`manifest_schema.py`): new `preprocessing: str = ""` field on
  `DatasetManifest`, wired through `from_dict` (`d.get("preprocessing") or ""`),
  `to_dict`, the field-reference docstring, and the dataclass. Optional /
  back-compatible — a manifest with no `preprocessing` key still validates.
- **`registry.py::list_available_datasets()`**: each entry now carries
  `"preprocessing": raw.get("preprocessing", "")`.
- **All 19 manifest YAMLs**: populated `preprocessing:` (folded scalar, inserted
  before `publication:`) with 1–3 sentences distilled from each file's header
  comments + `expression_source.note` / `data_level` comments — raw data,
  normalization/transform/units, feature-ID handling (probe collapse, symbol
  mapping), curation/subsetting, and Path A/B. No invented details.
- **Tests:** `pytest -q` → **45 passed, 2 skipped** (the fastmcp + live-data
  skips, unchanged). Verified all 19 datasets report a non-empty `preprocessing`
  and `to_dict()` round-trips the key.
- **Release commit `b46392c`** (pyproject `0.1.4`→`0.1.5` + wheel); pushed to
  **both** `github` (`7f9ab59..b46392c`) and `hf` (`7f9ab59..b46392c`).
- **Wheel** `biodata_registry-0.1.5-py3-none-any.whl`, **sha256
  `958f498b7880aef0d4558b102534ad357f850dd6b5755c2808c78973acfc05ec`**, 19
  manifests. Built with `uv build`. Isolated `uv pip install` → version 0.1.5,
  19 datasets, all `preprocessing` present, `get_integration_plan` importable.
- **Consumer pin (DecoupleRpy_Agent re-pins 0.1.4 → 0.1.5, folds in the pending
  Sears 0.1.4 bump):**
  `https://huggingface.co/anne-voigt/biodata-registry/resolve/b46392c86a6d3d3a5a9ead8593e9f400131f699c/biodata_registry-0.1.5-py3-none-any.whl`
  `--hash=sha256:958f498b7880aef0d4558b102534ad357f850dd6b5755c2808c78973acfc05ec`
  Resolve URL verified **HTTP 200** + sha match.

---

## 2026-06-22 session — 0.1.4 released (GSE205154 manifests in a consumable wheel)

Cut **0.1.4** so the 3 GSE205154 manifests ship in a wheel. Same publish path as
0.1.1–0.1.3 (the `huggingface-cli upload` in `scripts/release.sh` 403s on the
read-only API token → wheel is git-tracked at repo root + `git push hf`).

- **Wheel** `biodata_registry-0.1.4-py3-none-any.whl`, **sha256
  `9ac0c505d338893b8d5a42d879758ca69c8a4d2b3556b8f66aec19d8f90f8ba0`**, bundles
  **19 manifests** (incl. the 3 GSE205154). Built with `uv build`.
- **Release commit `0feb253`** (pyproject `0.1.3`→`0.1.4` + wheel); pushed to
  **both** `github` (`a6e46c9..0feb253`) and `hf` (`5654e86..0feb253`, the wheel
  host the resolve URL serves).
- **Verified:** isolated `uv pip install` of the wheel → version 0.1.4, 19
  datasets, the 3 GSE205154 load + validate, `get_integration_plan` importable.
  Resolve URL returns 200 + matching sha.
- **Consumer pin (DecoupleRpy_Agent re-pins to this — folded into the gradio-6
  migration, not done here):**
  `https://huggingface.co/anne-voigt/biodata-registry/resolve/0feb253d7df8c79341ef6b16f17097221bf4721c/biodata_registry-0.1.4-py3-none-any.whl`
  `--hash=sha256:9ac0c505d338893b8d5a42d879758ca69c8a4d2b3556b8f66aec19d8f90f8ba0`
- **Re-pin DONE (2026-06-22):** the gradio-6 migration had already shipped, so
  the re-pin was done standalone — DecoupleRpy_Agent `requirements.txt`/`.in`
  bumped 0.1.3 → 0.1.4 and pushed to prod (`202ae05`). ⚠️ Staged-paused (prod on
  cpu quota, no rebuild yet) and dev left at 0.1.3 → not yet validated on a live
  Space.

---

## 2026-06-22 session — GSE205154 h5ads uploaded (3 variants now LIVE); manifests de-placeholdered

The 3 GSE205154 (Sears) h5ads were built and **uploaded to
`anne-voigt/pdac-research-data`** — the 3 datasets are now loadable (the
expression_source URLs were placeholders until today).

- **Upload mechanism (important — same read-only-API gotcha as the wheels):** the
  cached `huggingface_hub` API token is **read-only** on the dataset repo — both a
  direct commit AND a `create_pr=1` PR return **403**. **`git push` has write**
  (verified via an empty-commit `--dry-run`), so the h5ads were published the same
  way the wheels are: `GIT_LFS_SKIP_SMUDGE=1` shallow-clone of
  `huggingface.co/datasets/anne-voigt/pdac-research-data`, `git lfs track` the 3
  new filenames (the repo tracks `.h5ad` by explicit filename, not a `*.h5ad`
  glob — must add each), copy files in, commit, `git push origin main`
  (`aadc2a0..ff14b87`, 256 MB LFS). Built via the assemble scripts' `--dry-run`
  (writes locally, skips the failing API upload).
- **Verified:** all 3 resolve URLs return **HTTP 200** with exact built sizes
  (`gse205154_sears` / `_counts` 85385414 B, `_tmm` 85446304 B); local builds
  load as 289 × 60554 AnnData (obs tumor_type/tissue/cell_type/sample_title,
  var.index = versioned Ensembl, var['SYMBOL']).
- **Manifests de-placeholdered:** removed the "PLACEHOLDER … URL will 404"
  language from all 3 `expression_source.note` blocks + dropped the matching
  placeholder limitation bullet; notes now record the 2026-06-22 upload + rebuild
  script. Still validate clean (0 errors); 45 pass / 2 skip.
- **`BIODATA_REGISTRY_COMMIT`** in `DecoupleRpy_Agent/scripts/_gse205154_sears_common.py`
  set to `533906d` (committed locally on the agent's `fix/gradio-6-migration`).
- **Still pending:** cut a new wheel + re-pin DecoupleRpy_Agent so the agent
  *sees* these 3 (it still pins 0.1.3). Gated on the agent's in-flight gradio-6
  migration / paused prod Space — not done this session.

---

## 2026-06-21 session — GSE205154 (Sears lab, OHSU) bulk RNA-seq added (3 variants) + anni-voigt script reconciliation

Added the Sears lab PDAC bulk RNA-seq cohort — **GSE205154**, the bulk-RNA-seq
subseries of SuperSeries **GSE281129** (PMID 39789181, Brenden-Colson Center /
OHSU). 289 FFPE primary + metastatic PDAC tumors. **Registry now has 19
manifests.** (The other GSE281129 subseries, GSE281005, is TCRβ-seq — no
expression modality, out of scope.)

- **3 sibling manifests — one 289-sample cohort, three quantifications (never pool):**
  - `gse205154_sears` — gene-level TPM → `tpm`, Path B (limma/ttest)
  - `gse205154_sears_counts` — tximport estimated counts rounded int32 → `raw_counts`, Path A (DESeq2)
  - `gse205154_sears_tmm` — edgeR TMM (not log-scaled) → `normalized`, Path B
  All three: `bulk_rnaseq`, human, `feature_id_type: ensembl_gene_id` (versioned
  ENSG in var.index, HGNC in `var['SYMBOL']`), obs indexed by GSM with tumor_type
  (Primary 218 / Met 71), tissue (anatomical site), cell_type, sample_title.
  Validate clean (0 errors / 0 warnings); offline suite 45 pass / 2 skip.
- **Key refusal baked in:** the liver-vs-lung metastatic-tropism grouping that
  defines the paper's signature is **NOT in GEO metadata** (clinical chart review;
  raw data dbGaP phs003597). Manifests refuse to fabricate it from
  `tissue`/`tumor_type`. No survival fields deposited → survival workflow disabled.
- **Caveats encoded:** 7/289 samples are `-F` (fibroblast) suffixed yet
  GEO-annotated "scraped tumor"/"Primary"; `tissue` has a LymphNode/Lymph Node
  split + one NA; the counts variant notes that rounding kallisto estimates is an
  approximation of the proper tximport→DESeq2 length-offset workflow; TMM carries
  the `TMM_pass_filter` gene flag into var.
- **expression_source = PLACEHOLDER HF URLs** (`gse205154_sears*.h5ad` at
  `anne-voigt/pdac-research-data`) — **not built/uploaded yet; URLs 404 until
  then.** These 3 datasets are registered but not yet usable.
- **Assembly scripts written (`DecoupleRpy_Agent/scripts/`):**
  `_gse205154_sears_common.py` (shared builder — supplementary-TSV → AnnData,
  joins GEO obs by `!Sample_title` == ST-id) + 3 thin wrappers
  `assemble_gse205154_sears{,_counts,_tmm}.py`. Verified end-to-end via
  `--dry-run` (289 × 60554, correct dtypes, provenance stamped to `.uns`); the
  upload step needs HF auth. NB: those files are committed **on the agent's
  `fix/gradio-6-migration` branch** (it had unrelated gradio WIP); agent repo not
  pushed (origin = prod Space).
- **anni-voigt → anne-voigt reconciliation:** the 2026-06-12 note claimed "no
  anni-voigt references remain", but 7 `assemble_*.py` still hardcoded
  `anni-voigt/pdac-research-data` (worked only via HF's username redirect — both
  resolve to the *same* file, confirmed identical size). Fixed in
  `assemble_{gse15471,gse17891,cptac_pda,paca_ca,gse21501,gse57495,nones}.py`.
  Now genuinely none remain.
- **Pending follow-ups:** (1) build + upload the 3 h5ads (run scripts without
  `--dry-run`, needs HF auth); (2) release a new wheel + re-pin DecoupleRpy_Agent
  (or pin a git commit) so the agent can consume them; (3) set
  `BIODATA_REGISTRY_COMMIT` in the shared builder to the manifests' commit hash.
- **Pushed to `github` (`avoigt1121/biodata-registry`).** HF wheel host
  (`origin`/`hf`) NOT bumped — no wheel cut this session.

---

## 2026-06-19 session — 0.1.3 released (Gate 6 confound hardening, ADR-0001 Case 3)

Hardened `get_integration_plan`'s confound gate (`_confound_separates`): it now
refuses (`CONFOUNDED_DESIGN`) when a requested cohort can supply **neither** arm
of a specified contrast — the design factor is absent from its metadata, or its
declared arms are disjoint from the requested pair. Previously it refused only
when *no* cohort could express both arms, so a Bailey-subtype contrast across a
Bailey-labelled cohort (`paca_au_rnaseq`, has both arms) + an unlabelled one
(`tcga_paad`, no `membership.ordered`) returned `early` and would silently
become a single-cohort result. Partial imbalance (one cohort skewed but still
contributing an arm) is still allowed — the batch covariate's job. Reason text +
module/function docstrings updated.

- **Tests:** +4 in `test_integration_plan.py` (factor-absent → refuse,
  disjoint-arms → refuse, real `paca_au_rnaseq`+`tcga_paad` Bailey case →
  refuse, partial-imbalance → not-refused). 26 integration + full suite 46
  pass / 1 skip; ruff clean.
- **Release:** `pyproject.toml` `0.1.2`→`0.1.3`; wheel
  `biodata_registry-0.1.3-py3-none-any.whl` (sha256
  `b90f7efc9e5cc776287ae0d5a0278e32266a32c39aa79801dcfb8ed3bdb73e9c`)
  git-tracked at repo root, pushed to `hf` + `github` (same git-push publish
  path as 0.1.1/0.1.2 — the HF API token is read-only). Consumer pin
  (DecoupleRpy_Agent): `.../resolve/<this release commit>/biodata_registry-0.1.3-py3-none-any.whl`.
- **Why now:** ADR-0001 T6 dev validation (DecoupleRpy_Agent) surfaced that
  Case 3 returned `early` instead of `refuse`. This closes that gap
  deterministically at the registry (plan-level), the single source of truth.

---

## 2026-06-19 session — integration engine merged + released as 0.1.2 (ADR-0001 T2 release)

`feat/integration-plan` **merged to `main`** and **released as wheel `0.1.2`** —
this closes the ADR-0001 T2 release. The wheel ships as a git-tracked artifact at
the repo root and is published via `git push hf` (the HF **API** token is
read-only, so `scripts/release.sh`'s `huggingface-cli upload` step is bypassed —
same pattern as 0.1.0/0.1.1).

- **Merge:** `feat/integration-plan` (`31ad048`→`c464404`) fast-forwarded into
  `main`; pushed to `github` (`89b9b12..cbc083a`, **closes the PR**) and `hf`
  (`6beb787..cbc083a`).
- **Release commit `cbc083a`:** bump `pyproject.toml` `0.1.1`→`0.1.2` + add
  `biodata_registry-0.1.2-py3-none-any.whl` (70134 bytes).
- **Consumer pin (DecoupleRpy_Agent T4 re-pins to this):**
  `biodata-registry @ https://huggingface.co/anne-voigt/biodata-registry/resolve/cbc083a5cd9dbe79e6740a6b64c4dc8c0639f113/biodata_registry-0.1.2-py3-none-any.whl`
  — sha256 `607a14b060ddd3fb9b5a889742b2e6c01d8f67b11c1905cfbea04dcc796082ad`.
  Verified served over the HF resolve endpoint (200, 70134 bytes, sha matches the
  built wheel).
- **Pre-release verification:** 42/42 tests green (22 integration + 20 registry)
  against the source; the built wheel re-checked in an isolated install
  (`get_integration_plan` importable, 16 manifests bundled, integration.py +
  server.py present).
- **Next (DecoupleRpy_Agent, this is now unblocked):** T4 — re-pin
  `requirements.txt` to the URL above + add the `dataset_get_integration_plan`
  wrapper tool. Then T5 (`decoupler_meta_analyze` + A→B→refuse wiring).

---

## 2026-06-18 session — cross-dataset integration engine (ADR-0001 Phase 1, step 2)

Added the cross-dataset compatibility decision function + a 5th MCP tool.
**On feature branch `feat/integration-plan` (commit `31ad048`), pushed to GitHub
with an open PR — NOT merged to main, NOT in a wheel.** Wheel build / version
bump / consumer re-pin are deliberately deferred to the release task (ADR
T4/T6). *(Superseded 2026-06-19: merged to `main` + released as 0.1.2 — see the
entry above.)*

- **New module `biodata_registry/integration.py`**:
  `get_integration_plan(dataset_ids, design_factor=None, test_group=None,
  control_group=None)` — a **pure function of manifest metadata** (loads no
  data). Decides `mode` ∈ `early` (pool expression, `dataset_id` as batch
  covariate) / `late` (meta-analyze per-dataset) / `refuse`. Returns `reason`
  (agent surfaces verbatim), `shared_feature_space`, `requires_probe_collapse`,
  `requires_ortholog_mapping`, `batch_key`, `poolable_data_level`,
  `per_dataset`, `refusal_rules_triggered`. The pure engine
  `plan_for_manifests(manifests, ...)` is split out so it's unit-testable
  against constructed `DatasetManifest` objects without the registry.
- **6-gate resolution** (first failing gate decides; short-circuit on refuse):
  1 arity (`NOT_MULTI`), 2 organism/ortholog bridge (`CROSS_ORGANISM_NO_BRIDGE`;
  mixed-but-bridgeable sets `requires_ortholog_mapping=True` and continues),
  3 shared `gene_symbol` space (`NO_SHARED_FEATURE_SPACE`), 4 modality
  (`CROSS_MODALITY`, v1 transcriptome-vs-proteome only), 5 `data_level`
  poolability (**D3**), 6 metadata confound (`CONFOUNDED_DESIGN`).
- **D3 (signed off):** early pooling requires the **same** `data_level` on every
  dataset *and* that level in `{raw_counts, log_expression, log_ratio, tpm,
  fpkm}`. `normalized` (scale unspecified) and `protein_abundance` are **never**
  early — even when equal across datasets they go `late`. Any level mismatch →
  `late`. early→late downgrades are NOT refusals (they carry a clear `reason`).
- **Gate 3 detail:** `gene_symbol` direct; `probe_id`+`requires_collapse=True`
  ok (sets `requires_probe_collapse`); `ensembl_gene_id`/`entrez_id` id-map;
  `probe_id`+`requires_collapse=False` → refuse; `protein_id` is treated as
  reachable (protein→gene) so the **modality** gate (4), not the feature gate,
  is what stops a transcriptome+proteome mix.
- **Spec gap resolved:** the signed-off signature was `get_integration_plan(
  dataset_ids)` but Gate 6 references "the requested contrast." Added **optional**
  `design_factor`/`test_group`/`control_group` kwargs (keeps the single-arg call
  valid). With no contrast supplied, Gate 6 **defers** (never fabricates
  `CONFOUNDED_DESIGN`) — matching the ADR registry-vs-specialist split (the
  sample-level confound check stays the specialist's runtime job). The confound
  check is also conservative: refuses only on positive metadata evidence that no
  single cohort can express both arms; sparse metadata defers.
- **5th MCP tool** in `server.py`: `@mcp.tool() get_integration_plan(...)`
  delegating to the module (docstring + module "Tools exposed" list updated).
  Exported from `__init__.py`. CLAUDE.md updated (now "Five MCP Tools" + an
  integration.py section) — genuine architecture change.
- **Tests** `tests/test_integration_plan.py`: 22 tests covering the full ADR
  checklist (equal raw_counts/log_expression → early; mixed → late; equal
  `normalized` → late *not* early; probe collapse=False → refuse; human+mouse no
  bridge → refuse; 1 dataset → NOT_MULTI; declared confound → CONFOUNDED_DESIGN;
  every plan has a non-empty reason) plus extras (protein_abundance→late,
  bridgeable cross-organism continues, cross-modality, confound-deferred,
  output-contract shape). Real ids used where the registry allows; synthetic
  manifests for the cases the all-human/no-proteomics 16-dataset registry can't
  express. **21 pass, 1 skip** (MCP-tool test `importorskip`s fastmcp, which
  isn't installed locally). Full repo suite stays green (41 passed, 2 skipped).
  Ran under CommandLineTools py3.9.6 — `from __future__ import annotations`
  keeps the `tuple[...]`/`list[...]` annotations lazy so it imports fine there.

---

## 2026-06-17 session — 0.1.1 wheel release

Cut **0.1.1** and shipped it to HF; both consumers re-pinned and deployed to
their prod Spaces.

- **Code fixes** (source commit `08980f0`): F821 forward-ref lint errors in
  `registry.py` resolved with a `TYPE_CHECKING` block; `manifest_schema.validate()`
  cyclomatic complexity 33 → 1 by extracting 8 `_check_*` helpers (behaviour
  identical, 20 tests pass).
- **Version** bumped `0.1.0 → 0.1.1` in `pyproject.toml`.
- **Wheel** `biodata_registry-0.1.1-py3-none-any.whl`, **sha256
  `f50073bc9a7ba9a1ee61b854b669bee1a7dc63d5e4f970ea5e0886520575fccd`**, 16
  manifests. Published to HF at commit **`ecbe4dc`** (HEAD); resolve URL:
  `https://huggingface.co/anne-voigt/biodata-registry/resolve/ecbe4dcfff57a5c887d32506a0c4e86a1196e9ec/biodata_registry-0.1.1-py3-none-any.whl`.
- **Upload mechanism (important):** the cached `huggingface_hub` API token is
  **read-only** (403 on a direct commit), but **`git push hf` has write access**.
  So the wheel ships as a git-tracked file at the repo root (`git add -f` +
  `git push hf main`), NOT via `hf upload`/`scripts/release.sh`'s API path. Do
  NOT rebuild before pinning — wheels aren't byte-reproducible; pin the hash of
  the exact file pushed.
- **Consumers re-pinned + deployed to prod:** DecoupleRpy_Agent (agent commit
  `3512127`, prod `3aa4e62`) and pdac-analysis-orchestrator (commit `3a41dfd`,
  prod). Verified the wheel installs from the HF URL on py3.12, loads 16
  datasets, and `validate()` returns valid.
- **Remaining:** one CC_F (`_check_dataset`, CC 42) in
  `tests/test_manifests_against_data.py` — test-only, not shipped in the wheel.

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

**Registry origin/main = `3bf0eb9`** (pushed 2026-06-14). Work this session since
the status doc: live-data test harness (`e836605`), COMPASS limitation (`d21e03b`),
Collisson subtypes (`dfbf8c4`), Nones symbol fix (`3bf0eb9`). DecoupleRpy_Agent
`requirements.txt` pin bumped to `3bf0eb9`, committed **locally only** (HEAD
`e027d3a`, 2 ahead of HF origin) — NOT pushed/deployed (its origin is the HF
Space). Deploy when ready by pushing DecoupleRpy_Agent origin.

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

> **Canonical open-items list is now `TODO.md`** (larger plans: `REGISTRY_TODO_PLANS.md`).
> The detail below is retained as the session log; add/triage new todos in `TODO.md`.

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

### 7. gse50827_nones Excel-corrupted gene symbols — DONE 2026-06-14
Fixed via Entrez-verified in-place relabel (pdacR featInfo has a clean ENTREZID
column): 12 date artifacts → DEC1, MARCH1..MARCH11, 1:1 no merges, no collisions.
Expression values untouched (no GEO re-assembly needed). Fixed h5ad re-uploaded;
provenance in adata.uns.symbol_fix_map. Script:
`DecoupleRpy_Agent/scripts/fix_gse50827_nones_symbols.py`.

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

16 manifests registered; all 16 now `expression_source.type: url` (format `h5ad`).

**This session (2026-06-18):** branch `feat/integration-plan` (integration
engine + 5th MCP tool + tests + doc sync) **pushed to the GitHub remote**
`avoigt1121/biodata-registry` with an open PR vs `main`. While pushing, GitHub
`main` was fast-forwarded `0c299ea → 89b9b12` (it had been 6 commits behind —
the unpushed 0.1.1 release work). NB: this clone's `origin`/`hf` remotes both
point to **HuggingFace** (`anne-voigt/biodata-registry`, wheel host); a separate
`github` remote was added this session for the GitHub canonical repo. Not yet
merged; no wheel cut — merge/release at ADR T4/T6 (then re-pin consumers).
