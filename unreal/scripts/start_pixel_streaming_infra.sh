#!/usr/bin/env bash
set -euo pipefail

# Starts Epic Pixel Streaming infrastructure (signaling/web).
# Required env:
#   PS_INFRA_ROOT=/srv/PixelStreamingInfrastructure
# Optional env:
#   PS_PUBLIC_IP=0.0.0.0
#   PS_HTTP_PORT=80
#   PS_HTTPS_PORT=443
#   PS_SIGNALING_PORT=8888

PS_INFRA_ROOT=${PS_INFRA_ROOT:-}
PS_PUBLIC_IP=${PS_PUBLIC_IP:-0.0.0.0}
PS_HTTP_PORT=${PS_HTTP_PORT:-80}
PS_HTTPS_PORT=${PS_HTTPS_PORT:-443}
PS_SIGNALING_PORT=${PS_SIGNALING_PORT:-8888}

if [[ -z "$PS_INFRA_ROOT" || ! -d "$PS_INFRA_ROOT" ]]; then
  echo "[start_pixel_streaming_infra] PS_INFRA_ROOT missing: $PS_INFRA_ROOT" >&2
  echo "Clone: https://github.com/EpicGamesExt/PixelStreamingInfrastructure" >&2
  exit 1
fi

cd "$PS_INFRA_ROOT"

if [[ -f package.json ]]; then
  npm install
fi

if [[ -x ./SignallingWebServer/platform_scripts/bash/start.sh ]]; then
  exec ./SignallingWebServer/platform_scripts/bash/start.sh \
    --httpPort "$PS_HTTP_PORT" \
    --httpsPort "$PS_HTTPS_PORT" \
    --streamerPort "$PS_SIGNALING_PORT" \
    --publicIp "$PS_PUBLIC_IP"
fi

if [[ -f ./SignallingWebServer/server.js ]]; then
  cd ./SignallingWebServer
  npm install
  exec node server.js --httpPort "$PS_HTTP_PORT" --httpsPort "$PS_HTTPS_PORT" --streamerPort "$PS_SIGNALING_PORT"
fi

echo "[start_pixel_streaming_infra] Could not find known start script/layout." >&2
exit 1
