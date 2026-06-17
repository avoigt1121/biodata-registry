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
- **Low — Push local `main` to `origin`.** Local is 2 commits ahead of
  `origin/main` (`release.sh` + the 0.1.0 wheel upload) as of 2026-06-17.

---

## Done (recent)

- 2026-06-14 — Collisson 2011 subtype labels added to `gse17891_collisson`
  (46/47 labeled; original labels, Route 1).
- 2026-06-14 — `gse50827_nones` Excel-corrupted gene symbols fixed
  (Entrez-verified relabel; 12 date artifacts).
- 2026-06-14 — Live-data test harness added (`test_manifests_against_data.py`);
  caught + fixed 2 real `missing_values` gaps.
- 2026-06-09 — TCGA-PAAD sample curation (Knudsen 2019, 150-barcode list).

_Full detail for any item: `memory.md`; larger plans: `REGISTRY_TODO_PLANS.md`._
