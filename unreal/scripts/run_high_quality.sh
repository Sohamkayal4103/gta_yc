#!/usr/bin/env bash
set -euo pipefail

# Launch packaged Unreal app with high quality + ray tracing defaults.
# Required env:
#   UE_APP_BIN=/srv/builds/MyGame/Binaries/Linux/MyGame
# Optional env:
#   UE_MAP=/Game/Maps/Main
#   UE_RES=2560x1440
#   UE_WINDOW_MODE=windowed|fullscreen (default: windowed)

UE_APP_BIN=${UE_APP_BIN:-}
UE_MAP=${UE_MAP:-}
UE_RES=${UE_RES:-2560x1440}
UE_WINDOW_MODE=${UE_WINDOW_MODE:-windowed}

if [[ -z "$UE_APP_BIN" || ! -x "$UE_APP_BIN" ]]; then
  echo "[run_high_quality] UE_APP_BIN missing or not executable: $UE_APP_BIN" >&2
  exit 1
fi

WIDTH=${UE_RES%x*}
HEIGHT=${UE_RES#*x}
MAP_ARG=()
if [[ -n "$UE_MAP" ]]; then
  MAP_ARG=("$UE_MAP")
fi

exec "$UE_APP_BIN" "${MAP_ARG[@]}" \
  -${UE_WINDOW_MODE} -ResX="$WIDTH" -ResY="$HEIGHT" \
  -RenderOffscreen=0 \
  -vulkan \
  -NoVSync \
  -fps=60 \
  -ExecCmds="r.RayTracing=1,r.Lumen.HardwareRayTracing=1,r.Nanite=1,sg.ViewDistanceQuality=4,sg.AntiAliasingQuality=4,sg.ShadowQuality=4,sg.GlobalIlluminationQuality=4,sg.ReflectionQuality=4,sg.PostProcessQuality=4,sg.TextureQuality=4,sg.EffectsQuality=4,sg.FoliageQuality=4"
