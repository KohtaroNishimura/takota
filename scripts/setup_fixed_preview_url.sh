#!/usr/bin/env bash
set -euo pipefail

HOSTNAME_VALUE="${1:-takota}"

if ! [[ "${HOSTNAME_VALUE}" =~ ^[a-zA-Z0-9][a-zA-Z0-9-]{0,62}$ ]]; then
  echo "ホスト名は英数字またはハイフンで指定してください: ${HOSTNAME_VALUE}" >&2
  exit 1
fi

if command -v hostnamectl >/dev/null 2>&1; then
  sudo hostnamectl set-hostname "${HOSTNAME_VALUE}"
else
  echo "hostnamectl が見つかりません。手動でホスト名を ${HOSTNAME_VALUE} に設定してください。" >&2
fi

if command -v apt-get >/dev/null 2>&1; then
  sudo apt-get update
  sudo apt-get install -y avahi-daemon
  sudo systemctl enable --now avahi-daemon
elif command -v systemctl >/dev/null 2>&1; then
  sudo systemctl enable --now avahi-daemon || true
fi

echo "固定URLを設定しました:"
echo "  http://${HOSTNAME_VALUE}.local:8080"
echo
echo "反映されない場合はラズパイを再起動してください:"
echo "  sudo reboot"
