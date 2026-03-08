#!/usr/bin/env bash
set -euo pipefail

# Convenience launcher: starts signaling infra + Unreal app in background.
# Requires env variables used by start_pixel_streaming_infra.sh and launch_pixel_streaming_app.sh

ROOT_DIR=$(cd "$(dirname "$0")" && pwd)
LOG_DIR=${UE_STACK_LOG_DIR:-"$ROOT_DIR/../logs"}
mkdir -p "$LOG_DIR"

INFRA_LOG="$LOG_DIR/infra.log"
APP_LOG="$LOG_DIR/app.log"

nohup "$ROOT_DIR/start_pixel_streaming_infra.sh" >"$INFRA_LOG" 2>&1 &
INFRA_PID=$!
echo "[run_pixel_streaming_stack] Infra PID: $INFRA_PID (log: $INFRA_LOG)"

sleep 3

nohup "$ROOT_DIR/launch_pixel_streaming_app.sh" >"$APP_LOG" 2>&1 &
APP_PID=$!
echo "[run_pixel_streaming_stack] App PID: $APP_PID (log: $APP_LOG)"

echo "$INFRA_PID" >"$LOG_DIR/infra.pid"
echo "$APP_PID" >"$LOG_DIR/app.pid"

echo "[run_pixel_streaming_stack] Stack started."
