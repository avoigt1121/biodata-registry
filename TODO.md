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
- **Low — HF `origin` mirror may lag `main`.** As of 2026-06-19 both GitHub
  `github` (`avoigt1121/biodata-registry`) and the HF `origin`/`hf` mirror
  (`anne-voigt/biodata-registry`, the wheel host) have `main` synced at
  `cbc083a` (the 0.1.2 release). Re-push `main` to `hf` after any future wheel so
  the resolve URL's commit exists on the mirror.

---

## Done (recent)

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
