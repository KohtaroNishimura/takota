#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

export PATH="${HOME}/.local/bin:${HOME}/.cargo/bin:/usr/local/bin:/usr/bin:/bin:${PATH:-}"

# shellcheck source=scripts/lib_network.sh
. ./scripts/lib_network.sh

if ! command -v uv >/dev/null 2>&1; then
  echo "uv が見つかりません。先に uv をインストールしてください。" >&2
  exit 1
fi

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ".env がなかったため .env.example から作成しました。"
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

mkdir -p data

WAIT_FOR_NETWORK_SEC="${AUTOSTART_WAIT_FOR_NETWORK_SEC:-${WAIT_FOR_NETWORK_SEC:-0}}"
if [ "${WAIT_FOR_NETWORK_SEC}" -gt 0 ]; then
  echo "ネットワークのIPv4アドレス取得を最大 ${WAIT_FOR_NETWORK_SEC} 秒待ちます。"
  if ! wait_for_preview_ipv4 "${WAIT_FOR_NETWORK_SEC}" >/dev/null; then
    echo "IPv4アドレスを取得できませんでした。プレビューサーバーは起動し、接続後に利用可能になります。" >&2
  fi
fi

echo "プレビューを起動します。停止するには Ctrl+C を押してください。"
echo "スマホ/PCで開く候補URL:"
print_preview_urls "${PREVIEW_PORT:-8080}" | sed 's/^/  /' || true
echo

exec uv run takota-people-flow \
  --track \
  --preview-server \
  --run-forever \
  --no-table
