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
STAGE_WAIT_SEC="${TETHER_RECOVERY_STAGE_WAIT_SEC:-30}"
CONNECTION_NAME="${TETHER_CONNECTION_NAME:-}"
REQUIRE_CONNECTION_NAME="${TETHER_RECOVERY_REQUIRE_CONNECTION_NAME:-true}"
RESTART_PREVIEW_SERVICE="${TETHER_RECOVERY_RESTART_PREVIEW_SERVICE:-false}"
PREVIEW_SERVICE_NAME="${TETHER_RECOVERY_PREVIEW_SERVICE_NAME:-takota-people-flow.service}"
RESTART_NETWORK_MANAGER="${TETHER_RECOVERY_RESTART_NETWORK_MANAGER:-true}"
NETWORK_MANAGER_RESTART_COMMAND="${TETHER_RECOVERY_NETWORK_MANAGER_RESTART_COMMAND:-sudo -n systemctl restart NetworkManager}"
REBOOT_ENABLED="${TETHER_RECOVERY_REBOOT_ENABLED:-false}"
REBOOT_COMMAND="${TETHER_RECOVERY_REBOOT_COMMAND:-sudo -n reboot}"

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

requires_named_connection() {
  [ -n "${CONNECTION_NAME}" ] && [ "${REQUIRE_CONNECTION_NAME}" = "true" ]
}

has_active_connection() {
  local name="$1"

  nmcli -t -f NAME connection show --active |
    awk -v target="${name}" -F: '$1 == target { found = 1 } END { exit found ? 0 : 1 }'
}

has_required_network() {
  has_ipv4 || return 1

  if requires_named_connection; then
    has_active_connection "${CONNECTION_NAME}"
    return
  fi

  return 0
}

candidate_connection_names() {
  nmcli -t -f NAME,TYPE,AUTOCONNECT connection show |
    awk -F: '$3 == "yes" && $2 != "loopback" { print $1 }'
}

disconnected_device_names() {
  nmcli -t -f DEVICE,STATE device status |
    awk -F: '$2 == "disconnected" { print $1 }'
}

non_target_active_wifi_connections() {
  local target="$1"

  nmcli -t -f NAME,TYPE connection show --active |
    awk -v target="${target}" -F: '$2 == "802-11-wireless" && $1 != target { print $1 }'
}

disconnect_non_target_wifi_connections() {
  local connection

  requires_named_connection || return 0

  while IFS= read -r connection; do
    [ -n "${connection}" ] || continue
    log "対象外Wi-Fiを切断します: ${connection}"
    nmcli connection down id "${connection}" >/dev/null 2>&1 || true
  done < <(non_target_active_wifi_connections "${CONNECTION_NAME}")
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

wait_for_ipv4() {
  local timeout_sec="$1"
  local deadline

  deadline=$((SECONDS + timeout_sec))
  while [ "${SECONDS}" -le "${deadline}" ]; do
    if has_required_network; then
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

  return 1
}

recover_by_connection_up() {
  local connection

  log "段階1: 保存済み接続と未接続デバイスの再接続を試します。"
  nmcli networking on >/dev/null 2>&1 || true
  nmcli radio wifi on >/dev/null 2>&1 || true
  disconnect_non_target_wifi_connections
  nmcli device wifi rescan >/dev/null 2>&1 || true
  connect_disconnected_devices

  if [ -n "${CONNECTION_NAME}" ]; then
    bring_up_connection "${CONNECTION_NAME}" || true
  else
    while IFS= read -r connection; do
      bring_up_connection "${connection}" || true
      has_required_network && break
    done < <(candidate_connection_names)
  fi
}

recover_by_wifi_cycle() {
  log "段階2: Wi-Fiをoff/onして再スキャンします。"
  nmcli radio wifi off >/dev/null 2>&1 || true
  sleep 3
  nmcli radio wifi on >/dev/null 2>&1 || true
  sleep 3
  nmcli device wifi rescan >/dev/null 2>&1 || true
  recover_by_connection_up
}

recover_by_network_manager_restart() {
  if [ "${RESTART_NETWORK_MANAGER}" != "true" ]; then
    log "段階3: NetworkManager再起動は無効です。"
    return 0
  fi

  log "段階3: NetworkManagerを再起動します。"
  if ! ${NETWORK_MANAGER_RESTART_COMMAND}; then
    log "NetworkManager再起動に失敗しました: ${NETWORK_MANAGER_RESTART_COMMAND}"
  fi
  sleep 10
  disconnect_non_target_wifi_connections
  recover_by_connection_up
}

recover_by_reboot() {
  if [ "${REBOOT_ENABLED}" != "true" ]; then
    log "最終段階: rebootは無効です。"
    return 0
  fi

  log "最終段階: 復旧できないため再起動します。"
  if ! ${REBOOT_COMMAND}; then
    log "再起動コマンドに失敗しました: ${REBOOT_COMMAND}"
  fi
}

try_recover() {
  log "IPv4アドレスが消えています。テザリング再接続を段階的に試します。"

  recover_by_connection_up
  wait_for_ipv4 "${STAGE_WAIT_SEC}" && return 0

  recover_by_wifi_cycle
  wait_for_ipv4 "${STAGE_WAIT_SEC}" && return 0

  recover_by_network_manager_restart
  wait_for_ipv4 "${RECOVER_WAIT_SEC}" && return 0

  log "まだIPv4アドレスを取得できません。iPhone側のインターネット共有が有効か確認してください。"
  recover_by_reboot
  return 1
}

require_nmcli

log "テザリング復旧監視を開始します。確認間隔: ${CHECK_INTERVAL_SEC}秒"

while true; do
  if has_required_network; then
    sleep "${CHECK_INTERVAL_SEC}"
    continue
  fi

  sleep "${MISSING_CONFIRM_SEC}"
  if ! has_required_network; then
    try_recover || true
  fi

  sleep "${CHECK_INTERVAL_SEC}"
done
