#!/usr/bin/env bash
set -euo pipefail

# Launch packaged Unreal app wired to signaling server for Pixel Streaming.
# Required env:
#   UE_APP_BIN=/srv/builds/MyGame/Binaries/Linux/MyGame
# Optional env:
#   UE_MAP=/Game/Maps/Main
#   UE_SIGNALING_URL=ws://127.0.0.1:8888
#   UE_STREAMER_ID=realmcast-main
#   UE_RES=1920x1080

UE_APP_BIN=${UE_APP_BIN:-}
UE_MAP=${UE_MAP:-}
UE_SIGNALING_URL=${UE_SIGNALING_URL:-ws://127.0.0.1:8888}
UE_STREAMER_ID=${UE_STREAMER_ID:-realmcast-main}
UE_RES=${UE_RES:-1920x1080}

if [[ -z "$UE_APP_BIN" || ! -x "$UE_APP_BIN" ]]; then
  echo "[launch_pixel_streaming_app] UE_APP_BIN missing or not executable: $UE_APP_BIN" >&2
  exit 1
fi

WIDTH=${UE_RES%x*}
HEIGHT=${UE_RES#*x}
MAP_ARG=()
if [[ -n "$UE_MAP" ]]; then
  MAP_ARG=("$UE_MAP")
fi

exec "$UE_APP_BIN" "${MAP_ARG[@]}" \
  -RenderOffscreen -ForceRes -ResX="$WIDTH" -ResY="$HEIGHT" \
  -PixelStreamingIP="${UE_SIGNALING_URL#ws://}" \
  -PixelStreamingPort="${UE_SIGNALING_URL##*:}" \
  -PixelStreamingURL="$UE_SIGNALING_URL" \
  -PixelStreamingID="$UE_STREAMER_ID" \
  -AudioMixer \
  -vulkan \
  -ExecCmds="r.RayTracing=1,r.Lumen.HardwareRayTracing=1,sg.ViewDistanceQuality=4,sg.ShadowQuality=4,sg.ReflectionQuality=4,sg.PostProcessQuality=4"
