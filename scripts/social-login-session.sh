#!/usr/bin/env bash
set -euo pipefail

platform="${1:-}"
if [[ -z "$platform" ]]; then
  echo "usage: $0 <weibo|bili|xhs|zhihu|dy|ks> [display] [novnc_port] [debug_port]" >&2
  exit 2
fi

case "$platform" in
  weibo|wb) platform="weibo"; profile_platform="wb" ;;
  bili|bilibili) platform="bili"; profile_platform="bili" ;;
  xhs) platform="xhs"; profile_platform="xhs" ;;
  zhihu) platform="zhihu"; profile_platform="zhihu" ;;
  dy|douyin) platform="dy"; profile_platform="dy" ;;
  ks|kuaishou) platform="ks"; profile_platform="ks" ;;
  *) echo "unsupported platform: $platform" >&2; exit 2 ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
display="${2:-99}"
novnc_port="${3:-6080}"
debug_port="${4:-9222}"
runtime_dir="${repo_root}/tmp/social-login/${platform}"
session_name="social-login-${platform}"
tailnet_host="${TAILNET_HOST:-}"

if [[ -z "$tailnet_host" ]] && command -v tailscale >/dev/null 2>&1; then
  tailnet_host="$(tailscale ip -4 2>/dev/null | sed -n '1p' || true)"
fi

tailnet_host="${tailnet_host:-100.115.253.20}"

if ! command -v tmux >/dev/null 2>&1; then
  echo "tmux is required to keep the login browser alive after this command exits" >&2
  exit 1
fi

mkdir -p "$runtime_dir"

if tmux has-session -t "$session_name" 2>/dev/null; then
  tmux kill-session -t "$session_name"
fi

rm -f "${runtime_dir}/session.env"

tmux new-session -d -s "$session_name" \
  "cd '$repo_root' && scripts/social-login-runner.sh '$platform' '$display' '$novnc_port' '$debug_port'"

ready=0
for _ in {1..60}; do
  if [[ -f "${runtime_dir}/session.env" ]] \
    && curl -fsS --max-time 2 "http://127.0.0.1:${debug_port}/json/version" >/dev/null \
    && curl -fsS --max-time 2 "http://127.0.0.1:${novnc_port}/vnc.html" >/dev/null; then
    ready=1
    break
  fi

  if ! tmux has-session -t "$session_name" 2>/dev/null; then
    echo "login session exited during startup; inspect logs in ${runtime_dir}" >&2
    exit 1
  fi

  sleep 0.5
done

if [[ "$ready" -ne 1 ]]; then
  echo "login session did not become ready; inspect tmux session ${session_name} and logs in ${runtime_dir}" >&2
  exit 1
fi

cat <<EOF
Started social login session for ${platform}

Profile:
  ${repo_root}/browser_data/cdp_${profile_platform}_user_data_dir

Local noVNC:
  http://127.0.0.1:${novnc_port}/vnc.html

Tailnet noVNC:
  http://${tailnet_host}:${novnc_port}/vnc.html

Chrome debug endpoint:
  http://127.0.0.1:${debug_port}/json/version

tmux:
  ${session_name}

Logs and session metadata:
  ${runtime_dir}

Stop with:
  scripts/social-login-stop.sh ${platform}
EOF
