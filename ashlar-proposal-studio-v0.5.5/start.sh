#!/bin/sh
set -eu

case "${ASHLAR_SERVICE:-web}" in
  web)
    exec streamlit run app.py \
      --server.address=0.0.0.0 \
      --server.port="${PORT:-8080}" \
      --server.headless=true \
      --browser.gatherUsageStats=false
    ;;
  api)
    exec uvicorn api.main:app --host 0.0.0.0 --port "${PORT:-8080}"
    ;;
  worker)
    exec python worker.py
    ;;
  *)
    echo "Unknown ASHLAR_SERVICE=${ASHLAR_SERVICE}. Use web, api or worker." >&2
    exit 2
    ;;
esac
