#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
state_dir="$project_root/.local/demo-share"
log_file="$state_dir/run.log"
service_label='com.sitewatch.lct.demo-share'

running_pid() {
  local saved_pid
  saved_pid="$(launchctl list "$service_label" 2>/dev/null |
    sed -n 's/.*"PID" = \([0-9][0-9]*\);/\1/p')"
  if [[ -z "$saved_pid" ]] || ! kill -0 "$saved_pid" 2>/dev/null; then
    return 1
  fi
  printf '%s\n' "$saved_pid"
}

print_link() {
  local link
  link="$(sed -n 's/^SHARE_LINK=//p' "$log_file" 2>/dev/null | tail -n 1)"
  if [[ -n "$link" ]]; then
    printf '%s\n' "$link"
    return 0
  fi
  return 1
}

case "${1:-}" in
  start)
    if [[ "$(uname -s)" != Darwin ]]; then
      echo 'Persistent sharing currently requires macOS launchd.' >&2
      exit 1
    fi
    if running_pid >/dev/null; then
      echo 'Sharing is already running:'
      print_link || echo 'The share link is still being prepared.'
      exit 0
    fi
    mkdir -p "$state_dir"
    chmod 700 "$state_dir"
    umask 077
    if launchctl list "$service_label" >/dev/null 2>&1; then
      launchctl remove "$service_label"
    fi
    : >"$log_file"
    chmod 600 "$log_file"
    launchctl submit -l "$service_label" -o "$log_file" -e "$log_file" -- \
      /usr/bin/env "PATH=$PATH" /bin/bash "$project_root/scripts/demo-live.sh" --share
    for attempt in {1..180}; do
      if running_pid >/dev/null && print_link; then
        echo 'The secret link works while this Mac is on and sharing is running.'
        exit 0
      fi
      if [[ "$attempt" -gt 5 ]] && ! running_pid >/dev/null; then
        echo 'Sharing did not start. Recent diagnostics:' >&2
        tail -n 20 "$log_file" >&2
        exit 1
      fi
      sleep 1
    done
    echo 'Sharing did not become ready within three minutes.' >&2
    exit 1
    ;;
  status)
    if running_pid >/dev/null; then
      print_link || echo 'Sharing is starting; no link yet.'
    else
      echo 'Sharing is not running.'
    fi
    ;;
  stop)
    if active_pid="$(running_pid)"; then
      launchctl remove "$service_label"
      for _ in {1..30}; do
        if ! kill -0 "$active_pid" 2>/dev/null; then
          break
        fi
        sleep 1
      done
      echo 'Sharing stopped. The old secret link no longer grants access.'
    else
      echo 'Sharing was not running.'
    fi
    ;;
  *)
    echo 'Usage: bash scripts/demo-share-control.sh start|status|stop' >&2
    exit 2
    ;;
esac
