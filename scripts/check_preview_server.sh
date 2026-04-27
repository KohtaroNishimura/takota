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

PORT="${PREVIEW_PORT:-8080}"

echo "サービス状態:"
systemctl --user is-active takota-people-flow.service || true
echo

echo "待ち受け確認:"
if ss -ltnp | grep -q ":${PORT} "; then
  ss -ltnp | grep ":${PORT} "
else
  echo "${PORT} 番ポートで待ち受けていません。"
fi
echo

echo "アクセスURL候補:"
print_preview_urls "${PORT}" || true
echo

echo "ラズパイ自身からのHTTP確認:"
python3 - <<PY
from urllib.request import urlopen

for url in ("http://127.0.0.1:${PORT}/",):
    try:
        with urlopen(url, timeout=5) as response:
            print(f"{url} -> HTTP {response.status}")
    except Exception as exc:
        print(f"{url} -> {type(exc).__name__}: {exc}")
PY
echo

echo "直近ログ:"
journalctl --user -u takota-people-flow.service -n 20 --no-pager
