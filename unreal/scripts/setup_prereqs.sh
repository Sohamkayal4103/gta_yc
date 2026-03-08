#!/usr/bin/env bash
set -euo pipefail

# Installs common host dependencies for Unreal + Pixel Streaming on Ubuntu/Debian.
# Safe to re-run.

if [[ ${EUID:-$(id -u)} -ne 0 ]]; then
  echo "[setup_prereqs] Run with sudo/root." >&2
  exit 1
fi

apt-get update
apt-get install -y \
  build-essential clang lld cmake ninja-build pkg-config \
  git curl wget unzip rsync jq \
  python3 python3-pip \
  nodejs npm \
  ffmpeg \
  mesa-utils \
  pciutils lshw net-tools iproute2 iputils-ping dnsutils \
  nvidia-utils-550 || true

# Optional but useful for reverse proxying/signaling hardening.
apt-get install -y nginx || true

cat <<'EOF'
[setup_prereqs] Done.
Next steps:
  1) Ensure NVIDIA driver + CUDA/NVENC runtime are installed and active.
  2) Install Unreal Engine 5.x (source build or launcher build).
  3) Prepare a packaged Linux build with Pixel Streaming plugin enabled.
  4) Run ./unreal/scripts/diagnostics.sh
EOF
