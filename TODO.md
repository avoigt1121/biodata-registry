# biodata-registry — TODO

Canonical open-items list for this repo. Session history stays in `memory.md`;
detailed implementation plans for the larger items live in
`REGISTRY_TODO_PLANS.md`. This file is the scannable backlog. Convention:
`High` / `Med` / `Low`; finished items move to `## Done` with a date.

Routing rule for this system: manifest/dataset-semantics → here ·
computation/tools/loaders → DecoupleRpy_Agent · routing/coordinator/eval →
pdac-analysis-orchestrator.

---

## Open

### Cross-dataset integration (ADR-0001)

- **Cross-reference (DecoupleRpy_Agent) — concordance routine NOW LIVE.**
  Registry 0.1.6 returns `mode="concordance"` for same-cohort variant requests;
  the agent's `decoupler_normalization_concordance` routine (built, was inert
  under 0.1.5) now acts on it instead of `decoupler_meta_analyze`. Deployed
  2026-06-24 (agent `fb2091e`) to dev (RUNNING) + prod (rebuilding) — see Done.
  Optional: drive a real `gse205154_sears` + `_tmm` query on a live Space for an
  end-to-end confirmation (couldn't be done from the release session — token
  lacked API access to the private dev Space).
- **Cross-reference (not registry-side)** — the agent-side wrapper, the
  meta-analysis engine, and the pooling/batch-correction code are
  DecoupleRpy_Agent's job (ADR-0001 Phase 1/2). The registry only decides
  compatibility; the specialist acts and does the sample-level confound guard.

### Schema / validation

- **Med — `gse50827_nones` fails `DatasetManifest.validate()`.** Survival-only
  dataset with `group_columns: []`. Fix is a design decision: relax the schema
  to allow an empty `group_columns`, or add a grouping column. See
  `REGISTRY_TODO_PLANS.md` §4.4-E.
- **Med — Automated semantics-vs-data verification** is the highest-leverage
  open item (discharges most of the §4.5 data-quality flags at once). Partly
  addressed 2026-06-14 via `tests/test_manifests_against_data.py` (opt-in,
  `RUN_LIVE_DATA_TESTS=1`, 16/16 live pass). Remaining work + per-dataset flags:
  `REGISTRY_TODO_PLANS.md` §4.4 / §4.5.

### Manifests / roadmap

- **Cross-reference (DecoupleRpy_Agent) — promote 0.1.4 to live prod.** Dev is
  RUNNING ✅ on 0.1.4 (`d19bfc9`, confirmed 2026-06-22), so the GSE205154 datasets
  load in the agent. Prod (`202ae05`) has the same pin but is staged-paused on the
  cpu quota — unpause + free a slot to bring it live. (Optional: drive an
  end-to-end "list datasets" query on dev for literal 19-dataset confirmation.)
- **Med — Add a `roadmap` key per manifest** + `scripts/collect_roadmap.py` to
  print a consolidated cross-dataset list of open items. (Paired with the same
  item in DecoupleRpy_Agent/TODO.md.)

### Blocked

- **Blocked — Chan-Seng-Yue 2020 (COMPASS) subtypes.** Open supplement has no
  machine-readable per-sample subtype table; donor-ID crosswalk to paca_ca is
  feasible (157/234) but no label values to join. Needs EGA DAA. See COMPASS
  section in `memory.md` + `REGISTRY_TODO_PLANS.md` §4.4-D.

### Cross-reference (not a registry-side fix)

- **Low — Live GPL-annotation fallback** in DecoupleRpy_Agent
  (`decoupler_annotate_probes_with_gpl`) is the agent-facing path for
  *unregistered* GEO datasets. All 16 registered manifests are pre-annotated, so
  this only resurfaces if a 17th manifest on GPL570/GPL13667 is added without
  precomputing. Tracked in DecoupleRpy_Agent/TODO.md.

### Low / housekeeping

- **Low — pdacR install broken on this machine** (`illuminaHumanv4.db`,
  `hgu219.db` fail via BiocManager on Bioc 3.22 / R 4.5.3). Individual `.rds`
  download workaround works fine for data extraction.
- **Low — No HF deployment for biodata-registry.** Not needed while
  DecoupleRpy_Agent imports the package directly.
- **Low — HF `origin` mirror may lag `main`.** As of 2026-06-24 both GitHub
  `github` (`avoigt1121/biodata-registry`) and the HF `origin`/`hf` mirror
  (`anne-voigt/biodata-registry`, the wheel host) have `main` synced at
  `261db0e` (the 0.1.6 release). Re-push `main` to `hf` after any future wheel so
  the resolve URL's commit exists on the mirror. NB: `git push hf` updates only
  the `hf/main` tracking ref, so `git status` may report "ahead of origin/main"
  even when the mirror is current — compare against `hf/main`, not `origin/main`.

---

## Done (recent)

- 2026-06-24 — **0.1.6 re-pin deployed to the agent.** DecoupleRpy_Agent
  re-pinned 0.1.5 → 0.1.6 (`fb2091e`), pushed to dev (`hf-dev`, RUNNING on 0.1.6
  after a transient cold-start 500 cleared) and prod (`origin`,
  `c9b0d3a..fb2091e`, rebuilding). Sibling-variant routing is now `concordance`
  (was `late`/meta-analyze). The live private-Space query wasn't drivable from
  the session (token lacked API access); verified via deterministic A/B + agent
  wrapper pass-through + user-confirmed dev RUNNING.
- 2026-06-24 — **0.1.6 released — same-cohort gate (`cohort_id`/`variant` +
  `concordance`/`DUPLICATE_COHORT`).** `get_integration_plan` routes sibling
  quantifications of one cohort (the GSE205154 TPM/counts/TMM trio) to
  `mode="concordance"` (compare, don't combine) instead of `late`/meta-analysis,
  and refuses `DUPLICATE_COHORT` when siblings are mixed with independent
  datasets. Two optional manifest fields `cohort_id`/`variant`; Gate 1b runs
  before the data_level gate. Release commit `261db0e` (wheel sha256
  `c4a21878…`, 19 manifests), pushed github + hf; resolve URL verified 200 + sha
  + size match. 56 pass / 2 skip. DecoupleRpy_Agent re-pinned 0.1.5 → 0.1.6
  (`fb2091e`, local — deploy pending; see Open).
- 2026-06-22 — **0.1.5 released — per-dataset `preprocessing` field (Item 3).**
  New optional `preprocessing: str` on the schema (wired through `from_dict`/
  `to_dict`), populated in all 19 manifests, surfaced in
  `list_available_datasets()`. Release commit `b46392c` (wheel sha256
  `958f498b…`), pushed github + hf; resolve URL verified 200 + sha match.
  45 pass / 2 skip. Consumer re-pin (DecoupleRpy_Agent 0.1.4 → 0.1.5, folds in
  the pending Sears bump) done same session.
- 2026-06-22 — **DecoupleRpy_Agent re-pinned to 0.1.4 + pushed to prod** (`202ae05`).
  Staged-paused (prod on cpu quota); dev left at 0.1.3 → re-pin unvalidated on a
  live Space yet (see Open cross-ref).
- 2026-06-22 — **0.1.4 released** (wheel `biodata_registry-0.1.4-py3-none-any.whl`,
  sha256 `9ac0c505…`, 19 manifests incl. the 3 GSE205154). Release commit
  `0feb253`, pushed to `github` + `hf`; resolve URL verified 200 + sha match.
  Consumer re-pin pending (folds into the agent's gradio-6 migration).
- 2026-06-22 — **GSE205154 (Sears) 3 h5ads uploaded + live.** Built via the
  assemble scripts, published to `anne-voigt/pdac-research-data` via `git push`
  (API token read-only / PR-blocked → 403; git push has write, same as the
  wheels). All 3 resolve URLs verified 200; manifests de-placeholdered. Remaining:
  wheel + consumer re-pin (above).
- 2026-06-21 — **GSE205154 (Sears/OHSU) bulk RNA-seq added** — 3 manifests
  (`gse205154_sears` TPM / `_counts` DESeq2 / `_tmm`), registry → 19. Assembly
  scripts in DecoupleRpy_Agent; 7 `anni-voigt` script refs reconciled to
  `anne-voigt`. Pushed to `github` (`533906d`).
- 2026-06-19 — **Integration engine merged + released as wheel 0.1.2** (closes
  ADR-0001 T2 release). `feat/integration-plan` fast-forwarded into `main`;
  pushed to `github` (PR closed) and `hf` (`cbc083a`). Consumer pin:
  `.../resolve/cbc083a5cd9dbe79e6740a6b64c4dc8c0639f113/biodata_registry-0.1.2-py3-none-any.whl`
  (sha256 `607a14b0…`), verified served. DecoupleRpy_Agent T4 re-pins next.
- 2026-06-18 — Cross-dataset compatibility engine (`get_integration_plan`) +
  5th MCP tool + 22 unit tests (ADR-0001 Phase 1, step 2). Pure metadata
  function; early/late/refuse with the D3 `data_level` poolability rule. On
  branch `feat/integration-plan` (`31ad048`); merged + released 2026-06-19 as
  0.1.2 (see above).
- 2026-06-14 — Collisson 2011 subtype labels added to `gse17891_collisson`
  (46/47 labeled; original labels, Route 1).
- 2026-06-14 — `gse50827_nones` Excel-corrupted gene symbols fixed
  (Entrez-verified relabel; 12 date artifacts).
- 2026-06-14 — Live-data test harness added (`test_manifests_against_data.py`);
  caught + fixed 2 real `missing_values` gaps.
- 2026-06-09 — TCGA-PAAD sample curation (Knudsen 2019, 150-barcode list).

_Full detail for any item: `memory.md`; larger plans: `REGISTRY_TODO_PLANS.md`._
