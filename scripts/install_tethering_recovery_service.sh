#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

SERVICE_DIR="${HOME}/.config/systemd/user"
SERVICE_FILE="${SERVICE_DIR}/takota-tethering-recovery.service"
PROJECT_DIR="$(pwd)"

mkdir -p "${SERVICE_DIR}"

cat > "${SERVICE_FILE}" <<SERVICE
[Unit]
Description=Takota iPhone Tethering Recovery
After=network.target

[Service]
Type=simple
WorkingDirectory=${PROJECT_DIR}
ExecStart=${PROJECT_DIR}/scripts/recover_tethering.sh
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
SERVICE

systemctl --user daemon-reload
systemctl --user enable takota-tethering-recovery.service

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

echo "テザリング復旧監視を有効化しました。今すぐ開始する場合:"
echo "  systemctl --user start takota-tethering-recovery.service"
echo
echo "状態確認:"
echo "  systemctl --user status takota-tethering-recovery.service"
echo
echo "ログ確認:"
echo "  journalctl --user -u takota-tethering-recovery.service -f"
