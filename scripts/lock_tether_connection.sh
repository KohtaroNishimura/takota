#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

TARGET_CONNECTION="${1:-${TETHER_CONNECTION_NAME:-}}"

if [ -z "${TARGET_CONNECTION}" ]; then
  echo "対象接続名を指定してください。" >&2
  echo "例: ./scripts/lock_tether_connection.sh iPhone" >&2
  exit 1
fi

if ! command -v nmcli >/dev/null 2>&1; then
  echo "nmcli が見つかりません。NetworkManager 環境で実行してください。" >&2
  exit 1
fi

if ! nmcli -t -f NAME connection show | awk -v target="${TARGET_CONNECTION}" -F: '$1 == target { found = 1 } END { exit found ? 0 : 1 }'; then
  echo "接続プロファイルが見つかりません: ${TARGET_CONNECTION}" >&2
  echo "nmcli connection show で正しい名前を確認してください。" >&2
  exit 1
fi

while IFS=: read -r name type; do
  [ "${type}" = "802-11-wireless" ] || continue

  if [ "${name}" = "${TARGET_CONNECTION}" ]; then
    echo "テザリング接続を優先します: ${name}"
    nmcli connection modify "${name}" connection.autoconnect yes connection.autoconnect-priority 100
  else
    echo "対象外Wi-Fiの自動接続を無効化します: ${name}"
    nmcli connection modify "${name}" connection.autoconnect no connection.autoconnect-priority 0
  fi
done < <(nmcli -t -f NAME,TYPE connection show)

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ".env がなかったため .env.example から作成しました。"
fi

set_env_value() {
  local key="$1"
  local value="$2"
  if grep -q "^${key}=" .env; then
    sed -i "s|^${key}=.*|${key}=${value}|" .env
  else
    printf '%s=%s\n' "${key}" "${value}" >> .env
  fi
}

set_env_value "TETHER_CONNECTION_NAME" "\"${TARGET_CONNECTION}\""
set_env_value "TETHER_RECOVERY_REQUIRE_CONNECTION_NAME" "true"

echo "テザリング接続だけを復旧対象に固定しました。"
echo "反映するには復旧監視サービスを再起動してください。"
echo "  systemctl --user restart takota-tethering-recovery.service"
