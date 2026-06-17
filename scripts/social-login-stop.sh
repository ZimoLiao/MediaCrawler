#!/usr/bin/env bash
set -euo pipefail

platform="${1:-}"
if [[ -z "$platform" ]]; then
  echo "usage: $0 <weibo|bili|xhs|zhihu|dy|ks>" >&2
  exit 2
fi

case "$platform" in
  wb) platform="weibo" ;;
  bilibili) platform="bili" ;;
  douyin) platform="dy" ;;
  kuaishou) platform="ks" ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime_dir="${repo_root}/tmp/social-login/${platform}"
env_file="${runtime_dir}/session.env"
session_name="social-login-${platform}"

if command -v tmux >/dev/null 2>&1 && tmux has-session -t "$session_name" 2>/dev/null; then
  tmux kill-session -t "$session_name" || true
fi

if [[ ! -f "$env_file" ]]; then
  echo "no active session metadata found for ${platform}: ${env_file}"
  exit 0
fi

# shellcheck disable=SC1090
source "$env_file"

for pid_var in BROWSER_PID NOVNC_PID X11VNC_PID FLUXBOX_PID XVFB_PID; do
  pid="${!pid_var:-}"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
done

sleep 1

for pid_var in BROWSER_PID NOVNC_PID X11VNC_PID FLUXBOX_PID XVFB_PID; do
  pid="${!pid_var:-}"
  if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
    kill -9 "$pid" 2>/dev/null || true
  fi
done

echo "Stopped social login session for ${platform}"
