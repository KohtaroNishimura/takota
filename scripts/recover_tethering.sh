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

CHECK_INTERVAL_SEC="${TETHER_RECOVERY_CHECK_INTERVAL_SEC:-10}"
MISSING_CONFIRM_SEC="${TETHER_RECOVERY_MISSING_CONFIRM_SEC:-20}"
RECOVER_WAIT_SEC="${TETHER_RECOVERY_WAIT_SEC:-60}"
CONNECTION_NAME="${TETHER_CONNECTION_NAME:-}"
RESTART_PREVIEW_SERVICE="${TETHER_RECOVERY_RESTART_PREVIEW_SERVICE:-false}"
PREVIEW_SERVICE_NAME="${TETHER_RECOVERY_PREVIEW_SERVICE_NAME:-takota-people-flow.service}"

log() {
  printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"
}

require_nmcli() {
  if ! command -v nmcli >/dev/null 2>&1; then
    log "nmcli が見つかりません。NetworkManager 環境で実行してください。"
    exit 1
  fi
}

has_ipv4() {
  list_preview_ipv4_addresses | grep -q .
}

candidate_connection_names() {
  nmcli -t -f NAME,TYPE,AUTOCONNECT connection show |
    awk -F: '$3 == "yes" && $2 != "loopback" { print $1 }'
}

disconnected_device_names() {
  nmcli -t -f DEVICE,STATE device status |
    awk -F: '$2 == "disconnected" { print $1 }'
}

bring_up_connection() {
  local name="$1"

  [ -n "${name}" ] || return 1
  log "接続を復旧します: ${name}"
  nmcli connection up id "${name}" >/dev/null 2>&1
}

connect_disconnected_devices() {
  local device

  while IFS= read -r device; do
    [ -n "${device}" ] || continue
    log "デバイスを再接続します: ${device}"
    nmcli device connect "${device}" >/dev/null 2>&1 || true
    has_ipv4 && break
  done < <(disconnected_device_names)
}

try_recover() {
  local connection
  local deadline

  log "IPv4アドレスが消えています。テザリング再接続を試します。"

  nmcli networking on >/dev/null 2>&1 || true
  nmcli radio wifi on >/dev/null 2>&1 || true
  nmcli device wifi rescan >/dev/null 2>&1 || true
  connect_disconnected_devices

  if [ -n "${CONNECTION_NAME}" ]; then
    bring_up_connection "${CONNECTION_NAME}" || true
  else
    while IFS= read -r connection; do
      bring_up_connection "${connection}" || true
      has_ipv4 && break
    done < <(candidate_connection_names)
  fi

  deadline=$((SECONDS + RECOVER_WAIT_SEC))
  while [ "${SECONDS}" -le "${deadline}" ]; do
    if has_ipv4; then
      log "テザリング接続が復旧しました。URL候補:"
      print_preview_urls "${PREVIEW_PORT:-8080}" | sed 's/^/  /' || true

      if [ "${RESTART_PREVIEW_SERVICE}" = "true" ]; then
        log "プレビューサービスを再起動します: ${PREVIEW_SERVICE_NAME}"
        systemctl --user restart "${PREVIEW_SERVICE_NAME}" || true
      fi
      return 0
    fi

    nmcli device wifi rescan >/dev/null 2>&1 || true
    sleep 5
  done

  log "まだIPv4アドレスを取得できません。iPhone側のインターネット共有が有効か確認してください。"
  return 1
}

require_nmcli

log "テザリング復旧監視を開始します。確認間隔: ${CHECK_INTERVAL_SEC}秒"

while true; do
  if has_ipv4; then
    sleep "${CHECK_INTERVAL_SEC}"
    continue
  fi

  sleep "${MISSING_CONFIRM_SEC}"
  if ! has_ipv4; then
    try_recover || true
  fi

  sleep "${CHECK_INTERVAL_SEC}"
done
