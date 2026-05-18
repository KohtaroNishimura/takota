#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SYSTEMCTL_COMMAND="$(command -v systemctl || true)"
REBOOT_COMMAND="$(command -v reboot || true)"
VISUDO_COMMAND="$(command -v visudo || true)"

if [ -z "${SYSTEMCTL_COMMAND}" ]; then
  echo "systemctl コマンドが見つかりません。" >&2
  exit 1
fi

if [ -z "${REBOOT_COMMAND}" ]; then
  echo "reboot コマンドが見つかりません。" >&2
  exit 1
fi

if [ -z "${VISUDO_COMMAND}" ]; then
  echo "visudo コマンドが見つかりません。" >&2
  exit 1
fi

SUDOERS_FILE="/etc/sudoers.d/takota-tethering-recovery-${USER}"
SUDOERS_LINE="${USER} ALL=(root) NOPASSWD: ${SYSTEMCTL_COMMAND} restart NetworkManager, ${REBOOT_COMMAND}"
TMP_FILE="$(mktemp)"
trap 'rm -f "${TMP_FILE}"' EXIT

printf '%s\n' "${SUDOERS_LINE}" > "${TMP_FILE}"
chmod 0440 "${TMP_FILE}"

if ! "${VISUDO_COMMAND}" -cf "${TMP_FILE}" >/dev/null; then
  echo "sudoers 設定の検証に失敗しました。" >&2
  exit 1
fi

sudo install -o root -g root -m 0440 "${TMP_FILE}" "${SUDOERS_FILE}"

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

set_env_value "TETHER_RECOVERY_RESTART_NETWORK_MANAGER" "true"
set_env_value "TETHER_RECOVERY_NETWORK_MANAGER_RESTART_COMMAND" "\"sudo -n ${SYSTEMCTL_COMMAND} restart NetworkManager\""
set_env_value "TETHER_RECOVERY_REBOOT_ENABLED" "true"
set_env_value "TETHER_RECOVERY_REBOOT_COMMAND" "\"sudo -n ${REBOOT_COMMAND}\""

echo "テザリング復旧用の NetworkManager 再起動と自動rebootを有効化しました。"
echo "反映するには復旧監視サービスを再起動してください。"
echo "  systemctl --user restart takota-tethering-recovery.service"
