#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

POWER_COMMAND="$(command -v poweroff || true)"
if [ -z "${POWER_COMMAND}" ]; then
  echo "poweroff コマンドが見つかりません。" >&2
  exit 1
fi

VISUDO_COMMAND="$(command -v visudo || true)"
if [ -z "${VISUDO_COMMAND}" ]; then
  echo "visudo コマンドが見つかりません。" >&2
  exit 1
fi

SUDOERS_FILE="/etc/sudoers.d/takota-preview-shutdown-${USER}"
SUDOERS_LINE="${USER} ALL=(root) NOPASSWD: ${POWER_COMMAND}"
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

set_env_value "PREVIEW_SHUTDOWN_ENABLED" "true"
set_env_value "PREVIEW_SHUTDOWN_COMMAND" "\"sudo -n ${POWER_COMMAND}\""

echo "プレビュー画面からの電源終了を有効化しました。"
echo "反映するにはサービスまたはプレビューを再起動してください。"
echo "  systemctl --user restart takota-people-flow.service"
