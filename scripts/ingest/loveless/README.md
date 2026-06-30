# Loveless single-cell ingestion — Phase 1 (.rds → h5ad)

Converts the Loveless integrated atlas (`scAtlas.rds.gz`, Zenodo
[`10.5281/zenodo.14199536`](https://zenodo.org/records/14199536)) into a
counts-only AnnData we can register. This is **Phase 1** of the Loveless TODO
(`biodata-registry/TODO.md` → "Dataset ingestion"); it unblocks the manifest,
which can only be written once we see the real `obs`/`var`.

> ⚠️ **Memory-bound, not a laptop job.** The atlas is >700k cells / ~33 GB
> compressed; `readRDS` holds the whole Seurat object in RAM. Run on a HF Job
> with **≥256 GB** RAM. No GPU needed. Confirmed flavor (`hf jobs hardware`,
> 2026-06): **`cpu-performance`** = 32 vCPU / 256 GB / 1024 GB disk / **$1.90/hr**.
> `cpu-xl` (124 GB / $1.00/hr) is the cheaper fallback only if the object fits
> counts-only.

## What it produces

| Artifact (uploaded to private `anne-voigt/pdac-research-data` under `loveless/`) | Purpose |
|---|---|
| `schema_report.txt` | R-side: assay names, obs columns + value counts. **Read first.** |
| `loveless_atlas.obs_summary.txt` | Python-side: per-obs-column cardinality + value counts. |
| `loveless_atlas_counts.h5ad` | Full atlas, **raw counts only** (corrected/scaled layers dropped). Offline reference/signature source — **not** a live-computed dataset. |
| `loveless_steele_subset.h5ad` | Pass 2 only: the Steele-cohort subset — the **analyzable** dataset to register. |

## Files here

- `convert_rds_to_h5ad.R` — loads the `.rds`, writes the schema report, extracts
  the raw `counts` layer + `obs` + gene/cell names to MatrixMarket/CSV. Drops
  corrected/scaled/integrated layers (the biggest RAM + output-size lever).
- `assemble_h5ad.py` — intermediates → gzip `.h5ad` (sparse throughout), plus the
  obs summary and an optional cohort subset.
- `run_job.sh` — one-shot in-container driver: download → R → Python → upload.
  Its dep-install step is a no-op when the baked image is used.
- `Dockerfile` — `FROM satijalab/seurat:5.5.1` + Python (anndata/scipy/pandas) +
  `hf` CLI, with the three scripts baked into `/payload`.

## Two-pass workflow

**Pass 1 — discover the schema** (no subset). We don't know the cohort/study
column or the patient/sample key yet, so don't guess — discover them:

```bash
HF_TOKEN=hf_xxx WORK=/data ./run_job.sh
```

Then read `loveless/schema_report.txt` + `loveless_atlas.obs_summary.txt` on the
dataset repo and identify:
- the **cohort/study** column (to subset the Steele cohort), and
- the **patient/sample** key — the pseudobulk aggregation key (the critical
  manifest field).

**Pass 2 — emit the analyzable subset** (re-run with the discovered column):

```bash
HF_TOKEN=hf_xxx SUBSET_COL=<cohort_col> SUBSET_VALUE=<steele_label> ./run_job.sh
```

## Launching on a HF Job

`hf jobs run` runs a **pre-built image** — it does not mount a local directory —
so the scripts have to live inside the image. Build + push the baked image once:

```bash
cd scripts/ingest/loveless
docker build --platform linux/amd64 -t <user>/loveless-convert:1 .   # x86: HF Jobs are amd64
docker push <user>/loveless-convert:1
```

**Pass 1 — discover the schema** (no subset). `--detach` returns a job id instead
of blocking for hours:

```bash
hf jobs run --detach \
  --flavor cpu-performance \
  --secrets HF_TOKEN=$HF_TOKEN \
  --timeout 6h \
  <user>/loveless-convert:1
```

**Pass 2 — emit the analyzable subset** (re-run with the discovered column/value):

```bash
hf jobs run --detach \
  --flavor cpu-performance \
  --secrets HF_TOKEN=$HF_TOKEN \
  --env SUBSET_COL=<cohort_col> --env SUBSET_VALUE=<steele_label> \
  --timeout 6h \
  <user>/loveless-convert:1
```

Follow it with `hf jobs logs <job_id>` (and `hf jobs ls` / `hf jobs inspect`). The
1024 GB job disk on `cpu-performance` holds the 33 GB download + intermediates +
outputs comfortably.

> No-build alternative: run stock `satijalab/seurat:5.5.1` and have the launch
> command `curl` the three raw scripts from this repo first — but the baked image
> is reproducible and avoids a network fetch mid-job, so prefer the Dockerfile.

## After Phase 1 — unblock the manifest

With the real `obs`/`var` in hand, write `biodata_registry/manifests/loveless_*.yaml`:
`accession: 10.5281/zenodo.14199536`, `modality: sc_rnaseq`, confirm
`feature_id_type: gene_symbol`, set `sample_id_column` to the patient/sample key,
`valid_workflows: [sc_annotation, pseudobulk_de, activity_scoring]`, refusal rules
(no cell-level p-values; never pool with bulk — the `CROSS_RESOLUTION` gate added
in 0.1.7 enforces that automatically). Validate against the hosted h5ad, then ship
as 0.1.8 and re-pin the agent.
