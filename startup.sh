#!/bin/sh
set -eu
if [ -n "${WEBSITE_SITE_NAME:-}" ]; then
  export GRANTSCOPE_DATA_DIR="${GRANTSCOPE_DATA_DIR:-/home/grantscope}"
  export GRANTSCOPE_RESEARCH_CACHE="${GRANTSCOPE_RESEARCH_CACHE:-/tmp/grantscope-private-research-v1}"
  export GRANTSCOPE_RESEARCH_ARCHIVE_DIR="${GRANTSCOPE_RESEARCH_ARCHIVE_DIR:-${GRANTSCOPE_DATA_DIR}/research_encrypted_v1}"
fi
exec python -m streamlit run app.py --server.address 0.0.0.0 --server.port "${PORT:-8000}" --server.headless true --browser.gatherUsageStats false --global.minCachedMessageSize 2147483647
