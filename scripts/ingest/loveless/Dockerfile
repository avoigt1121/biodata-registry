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
        python3 python3-pip curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Throwaway job image, so install into the system env (PEP 668 override on
# Debian/rocker). Keeps PATH simple — no venv activation needed at runtime.
RUN pip3 install --no-cache-dir --break-system-packages \
        anndata scipy pandas "huggingface_hub[cli]"

WORKDIR /payload
COPY convert_rds_to_h5ad.R assemble_h5ad.py subset_h5ad.py run_job.sh ./
RUN chmod +x convert_rds_to_h5ad.R assemble_h5ad.py subset_h5ad.py run_job.sh

# Default entry runs the full pipeline; override per-pass with -e SUBSET_COL/VALUE.
CMD ["bash", "-lc", "cd /payload && ./run_job.sh"]
