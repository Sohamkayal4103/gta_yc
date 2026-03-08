#!/usr/bin/env bash
set -euo pipefail

# Host diagnostics for Unreal + Pixel Streaming readiness.
# Checks: GPU driver, NVENC presence, ports, node/npm, websocket reachability hints.

UE_SIGNALING_HOST=${UE_SIGNALING_HOST:-127.0.0.1}
UE_SIGNALING_PORT=${UE_SIGNALING_PORT:-8888}
UE_HTTP_PORT=${UE_HTTP_PORT:-80}

hr() { printf '%*s\n' "${COLUMNS:-80}" '' | tr ' ' '-'; }
section() { hr; echo "[diag] $1"; hr; }

section "OS + Kernel"
uname -a || true
cat /etc/os-release || true

section "GPU / Driver"
if command -v nvidia-smi >/dev/null 2>&1; then
  nvidia-smi || true
  echo
  nvidia-smi --query-gpu=name,driver_version,vbios_version,encoder.stats.sessionCount,encoder.stats.averageFps,encoder.stats.averageLatency --format=csv,noheader || true
else
  echo "nvidia-smi not found"
fi

section "NVENC capability (ffmpeg)"
if command -v ffmpeg >/dev/null 2>&1; then
  ffmpeg -hide_banner -encoders 2>/dev/null | grep -E 'nvenc|h264_nvenc|hevc_nvenc' || true
else
  echo "ffmpeg not found"
fi

section "OpenGL/Vulkan availability"
command -v vulkaninfo >/dev/null 2>&1 && vulkaninfo --summary || echo "vulkaninfo not found"
command -v glxinfo >/dev/null 2>&1 && glxinfo | grep -E 'OpenGL vendor|OpenGL renderer|OpenGL version' || echo "glxinfo not found"

section "Node/npm"
node --version || true
npm --version || true

section "Port readiness"
if command -v ss >/dev/null 2>&1; then
  ss -lntup | grep -E ":(${UE_SIGNALING_PORT}|${UE_HTTP_PORT})\b" || true
else
  netstat -lntup 2>/dev/null | grep -E ":(${UE_SIGNALING_PORT}|${UE_HTTP_PORT})\b" || true
fi

section "HTTP reachability"
if command -v curl >/dev/null 2>&1; then
  curl -I --max-time 2 "http://${UE_SIGNALING_HOST}:${UE_HTTP_PORT}" || true
  curl -I --max-time 2 "http://${UE_SIGNALING_HOST}:${UE_SIGNALING_PORT}" || true
fi

section "Firewall snapshot"
command -v ufw >/dev/null 2>&1 && ufw status verbose || true

cat <<EOF
[diag] Complete.
Expected open ports for LAN/browser clients:
  - ${UE_HTTP_PORT}/tcp (Pixel Streaming player web)
  - ${UE_SIGNALING_PORT}/tcp (signaling websocket)
If TURN is used for WAN clients, also open TURN/TLS ports per your config.
EOF
