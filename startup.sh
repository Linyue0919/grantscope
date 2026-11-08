#!/bin/sh
set -eu
if [ -n "${WEBSITE_SITE_NAME:-}" ]; then
  export GRANTSCOPE_DATA_DIR="${GRANTSCOPE_DATA_DIR:-/home/grantscope}"
fi
exec python -m streamlit run app.py --server.address 0.0.0.0 --server.port "${PORT:-8000}" --server.headless true --browser.gatherUsageStats false
