#!/usr/bin/env bash
set -euo pipefail

platform="${1:?platform required}"
display="${2:?display required}"
novnc_port="${3:?novnc port required}"
debug_port="${4:?debug port required}"

case "$platform" in
  weibo|wb) platform="weibo"; profile_platform="wb"; start_url="https://weibo.com/login.php" ;;
  bili|bilibili) platform="bili"; profile_platform="bili"; start_url="https://www.bilibili.com/" ;;
  xhs) platform="xhs"; profile_platform="xhs"; start_url="https://www.xiaohongshu.com/explore" ;;
  zhihu) platform="zhihu"; profile_platform="zhihu"; start_url="https://www.zhihu.com/" ;;
  dy|douyin) platform="dy"; profile_platform="dy"; start_url="https://www.douyin.com/" ;;
  ks|kuaishou) platform="ks"; profile_platform="ks"; start_url="https://www.kuaishou.com/" ;;
  *) echo "unsupported platform: $platform" >&2; exit 2 ;;
esac

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
browser="${MEDIACRAWLER_BROWSER:-/home/lzmo/.cache/ms-playwright/chromium-1124/chrome-linux/chrome}"
display_name=":${display}"
vnc_port="$((5900 + display))"
profile_dir="${repo_root}/browser_data/cdp_${profile_platform}_user_data_dir"
runtime_dir="${repo_root}/tmp/social-login/${platform}"

mkdir -p "$profile_dir" "$runtime_dir"

cleanup() {
  for pid in "${browser_pid:-}" "${novnc_pid:-}" "${x11vnc_pid:-}" "${fluxbox_pid:-}" "${xvfb_pid:-}"; do
    if [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}
trap cleanup EXIT INT TERM

pkill -f "Xvfb ${display_name} " 2>/dev/null || true
pkill -f "x11vnc .*${display_name}" 2>/dev/null || true
pkill -f "novnc_proxy.*--listen 127.0.0.1:${novnc_port}" 2>/dev/null || true
pkill -f "${browser}.*--remote-debugging-port=${debug_port}.*${profile_dir}" 2>/dev/null || true

Xvfb "$display_name" -screen 0 1440x1000x24 -nolisten tcp >"${runtime_dir}/xvfb.log" 2>&1 &
xvfb_pid=$!

for _ in {1..40}; do
  [[ -S "/tmp/.X11-unix/X${display}" ]] && break
  sleep 0.25
done

env DISPLAY="$display_name" fluxbox >"${runtime_dir}/fluxbox.log" 2>&1 &
fluxbox_pid=$!

x11vnc -display "$display_name" -localhost -nopw -forever -shared -rfbport "$vnc_port" >"${runtime_dir}/x11vnc.log" 2>&1 &
x11vnc_pid=$!

/usr/share/novnc/utils/novnc_proxy --listen "127.0.0.1:${novnc_port}" --vnc "127.0.0.1:${vnc_port}" >"${runtime_dir}/novnc.log" 2>&1 &
novnc_pid=$!

sleep 1

env DISPLAY="$display_name" "$browser" \
  --user-data-dir="$profile_dir" \
  --remote-debugging-port="$debug_port" \
  --no-sandbox \
  --no-first-run \
  --no-default-browser-check \
  --disable-dev-shm-usage \
  --disable-gpu \
  --window-size=1440,1000 \
  "$start_url" >"${runtime_dir}/chromium.log" 2>&1 &
browser_pid=$!

cat >"${runtime_dir}/session.env" <<EOF
PLATFORM=${platform}
CRAWLER_PLATFORM=${profile_platform}
PROFILE_DIR=${profile_dir}
DISPLAY=${display_name}
NOVNC_URL=http://127.0.0.1:${novnc_port}/vnc.html
VNC_PORT=${vnc_port}
DEBUG_PORT=${debug_port}
XVFB_PID=${xvfb_pid}
FLUXBOX_PID=${fluxbox_pid}
X11VNC_PID=${x11vnc_pid}
NOVNC_PID=${novnc_pid}
BROWSER_PID=${browser_pid}
EOF

sleep 2
curl -fsS --max-time 3 "http://127.0.0.1:${debug_port}/json/version" >/dev/null
curl -fsS --max-time 3 "http://127.0.0.1:${novnc_port}/vnc.html" >/dev/null

echo "social login session ready for ${platform}"
wait "$browser_pid"
