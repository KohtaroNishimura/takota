#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

# shellcheck source=scripts/lib_network.sh
. ./scripts/lib_network.sh

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

echo "同じテザリング/Wi-Fiに接続したスマホまたはPCで、次のURLを開いてください。"
print_preview_urls "${PREVIEW_PORT:-8080}"
