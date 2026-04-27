#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_FILE="${SERVICE_DIR}/takota-people-flow.service"
PROJECT_DIR="$(pwd)"

mkdir -p "${SERVICE_DIR}"

cat > "${SERVICE_FILE}" <<SERVICE
[Unit]
Description=Takota People Flow Preview
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
Environment=AUTOSTART_WAIT_FOR_NETWORK_SEC=120
ExecStart=${PROJECT_DIR}/scripts/start_preview.sh
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
SERVICE

systemctl --user daemon-reload
systemctl --user enable takota-people-flow.service

if command -v loginctl >/dev/null 2>&1; then
  if loginctl enable-linger "${USER}"; then
    echo "ログインしていなくても user service が起動するように linger を有効化しました。"
  else
    echo "linger の有効化に失敗しました。必要なら次を実行してください:" >&2
    echo "  sudo loginctl enable-linger ${USER}" >&2
  fi
else
  echo "loginctl が見つかりません。起動後ログインなしで動かすには linger 設定を確認してください。" >&2
fi

echo "自動起動を有効化しました。今すぐ開始する場合:"
echo "  systemctl --user start takota-people-flow.service"
echo
echo "状態確認:"
echo "  systemctl --user status takota-people-flow.service"
echo
echo "ログ確認:"
echo "  journalctl --user -u takota-people-flow.service -f"
echo
echo "停止:"
echo "  systemctl --user stop takota-people-flow.service"
