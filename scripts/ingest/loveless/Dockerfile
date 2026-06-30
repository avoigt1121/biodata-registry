# Loveless Phase 1 conversion image — Seurat (R) + anndata (Python) + hf CLI,
# with the conversion scripts baked into /payload (no mounted dir needed).
#
# Build + push to a registry HF Jobs can pull (Docker Hub shown; GHCR works too):
#   cd scripts/ingest/loveless
#   docker build --platform linux/amd64 -t <user>/loveless-convert:1 .
#   docker push <user>/loveless-convert:1
# Then launch (see README.md): hf jobs run --flavor cpu-performance ... <user>/loveless-convert:1
#
# --platform linux/amd64 matters if you build on Apple Silicon — HF Jobs are x86.

FROM satijalab/seurat:5.5.1

# Python side for h5ad assembly + HF upload (the base image is R-only).
RUN apt-get update && apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps in an isolated venv — NOT the system env. The base image's
# `packaging` (and others) are apt-managed with no RECORD file, so pip cannot
# upgrade/uninstall them (`--break-system-packages` doesn't help). A venv sidesteps
# the clash entirely. Rscript stays on PATH (system); python3/pip/hf become the venv's.
ENV VENV=/opt/venv
RUN python3 -m venv "$VENV"
ENV PATH="$VENV/bin:$PATH"
RUN pip install --no-cache-dir anndata scipy pandas "huggingface_hub[cli]"

WORKDIR /payload
COPY convert_rds_to_h5ad.R assemble_h5ad.py subset_h5ad.py run_job.sh ./
RUN chmod +x convert_rds_to_h5ad.R assemble_h5ad.py subset_h5ad.py run_job.sh

# Default entry runs the full pipeline; override per-pass with -e SUBSET_COL/VALUE.
# Plain `bash -c` (not -lc) so the Docker-set PATH (venv first) isn't reset by
# /etc/profile; run_job.sh also re-asserts the venv on PATH defensively.
CMD ["bash", "-c", "cd /payload && ./run_job.sh"]
