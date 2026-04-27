#!/usr/bin/env bash

list_preview_ipv4_addresses() {
  if command -v ip >/dev/null 2>&1; then
    ip -o -4 addr show scope global up | awk '{ split($4, a, "/"); print a[1] }'
    return
  fi

  hostname -I | awk '{ for (i = 1; i <= NF; i++) if ($i !~ /:/) print $i }'
}

preview_hostname_url() {
  local port="${1:-8080}"
  local host_name

  host_name="$(hostname -s 2>/dev/null || hostname)"
  [ -n "${host_name}" ] || return 1
  echo "http://${host_name}.local:${port}"
}

wait_for_preview_ipv4() {
  local timeout_sec="${1:-0}"
  local deadline

  if [ "${timeout_sec}" -le 0 ]; then
    list_preview_ipv4_addresses | head -n 1
    return
  fi

  deadline=$((SECONDS + timeout_sec))
  while [ "${SECONDS}" -le "${deadline}" ]; do
    if list_preview_ipv4_addresses | grep -q .; then
      list_preview_ipv4_addresses | head -n 1
      return
    fi
    sleep 2
  done

  return 1
}

print_preview_urls() {
  local port="${1:-8080}"
  local found=0

  if preview_hostname_url "${port}"; then
    found=1
  fi

  while IFS= read -r ip_addr; do
    [ -n "${ip_addr}" ] || continue
    found=1
    echo "http://${ip_addr}:${port}"
  done < <(list_preview_ipv4_addresses)

  if [ "${found}" -eq 0 ]; then
    echo "IPv4アドレスがまだ取得できていません。テザリング接続後に ./scripts/show_preview_url.sh を実行してください。" >&2
    return 1
  fi
}
