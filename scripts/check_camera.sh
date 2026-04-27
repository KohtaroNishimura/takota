#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [ ! -f ".env" ]; then
  cp .env.example .env
  echo ".env がなかったため .env.example から作成しました。"
fi

uv run takota-people-flow \
  --check-stream \
  --max-frames 10
