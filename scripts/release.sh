#!/usr/bin/env bash
# Release biodata-registry as a wheel on Hugging Face.
#
# Why a wheel (not git): HF's git server can't serve pip's partial clone
# (--filter=blob:none), so `pip install git+https://huggingface.co/...` fails on
# Space builds. A wheel served over HF's resolve (HTTPS) URL installs cleanly and
# is hashable.
#
# Run this after bumping `version` in pyproject.toml when manifests/schema change.
# Requires: uv, and an HF login (huggingface-cli login, or HF_TOKEN) with write
# access to the repo.
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="anne-voigt/biodata-registry"

command -v uv >/dev/null || { echo "error: uv required (https://docs.astral.sh/uv/)" >&2; exit 1; }

echo "==> building wheel"
rm -rf dist
uv build --wheel --out-dir dist
WHL="$(ls dist/*.whl)"
BASE="$(basename "$WHL")"
SHA="$(shasum -a 256 "$WHL" | awk '{print $1}')"
echo "    $WHL"
echo "    sha256 $SHA"

echo "==> uploading to https://huggingface.co/$REPO (keeps old versions for old pins)"
uvx --from huggingface_hub huggingface-cli upload "$REPO" "$WHL" "$BASE" --repo-type model --commit-message "Release $BASE"

NEWREV="$(git ls-remote "https://huggingface.co/$REPO.git" HEAD | awk '{print $1}')"
echo
echo "==> done. Pin consumers to:"
echo "    biodata-registry @ https://huggingface.co/$REPO/resolve/$NEWREV/$BASE \\"
echo "        --hash=sha256:$SHA"
