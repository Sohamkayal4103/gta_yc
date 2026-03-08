#!/usr/bin/env bash
set -euo pipefail

# Build/package helper for Unreal projects (Linux target) with retries + verbose logs.
#
# Required env:
#   UE_ROOT=/opt/UnrealEngine-5.3
#   UE_PROJECT=/srv/MyGame/MyGame.uproject
# Optional env:
#   UE_BUILD_CONFIG=Shipping|Development (default: Shipping)
#   UE_ARCHIVE_DIR=/srv/builds/unreal (default: <project>/Saved/StagedBuilds/Linux)
#   UE_RETRIES=2
#   UE_RETRY_DELAY_SEC=25
#   UE_LOG_DIR=<project>/Saved/Logs

UE_ROOT=${UE_ROOT:-}
UE_PROJECT=${UE_PROJECT:-}
UE_BUILD_CONFIG=${UE_BUILD_CONFIG:-Shipping}
UE_ARCHIVE_DIR=${UE_ARCHIVE_DIR:-}
UE_RETRIES=${UE_RETRIES:-2}
UE_RETRY_DELAY_SEC=${UE_RETRY_DELAY_SEC:-25}
UE_LOG_DIR=${UE_LOG_DIR:-}

if [[ -z "$UE_ROOT" || -z "$UE_PROJECT" ]]; then
  echo "[build_package] Missing UE_ROOT or UE_PROJECT env vars." >&2
  exit 1
fi

if [[ ! -f "$UE_PROJECT" ]]; then
  echo "[build_package] UE_PROJECT not found: $UE_PROJECT" >&2
  exit 1
fi

RUN_UAT="$UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh"
if [[ ! -x "$RUN_UAT" ]]; then
  echo "[build_package] RunUAT not found or not executable: $RUN_UAT" >&2
  exit 1
fi

PROJECT_DIR=$(cd "$(dirname "$UE_PROJECT")" && pwd)
PROJECT_NAME=$(basename "$UE_PROJECT" .uproject)
ARCHIVE_DIR=${UE_ARCHIVE_DIR:-"$PROJECT_DIR/Saved/StagedBuilds/Linux"}
LOG_DIR=${UE_LOG_DIR:-"$PROJECT_DIR/Saved/Logs"}
mkdir -p "$LOG_DIR"

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG_FILE="$LOG_DIR/build_package_${PROJECT_NAME}_${STAMP}.log"

echo "[build_package] Project: $UE_PROJECT"
echo "[build_package] Config: $UE_BUILD_CONFIG"
echo "[build_package] Archive: $ARCHIVE_DIR"
echo "[build_package] Log file: $LOG_FILE"

attempt=1
while [[ "$attempt" -le "$UE_RETRIES" ]]; do
  echo "[build_package] Attempt $attempt/$UE_RETRIES"
  set +e
  "$RUN_UAT" BuildCookRun \
    -project="$UE_PROJECT" \
    -platform=Linux \
    -clientconfig="$UE_BUILD_CONFIG" \
    -build -cook -stage -pak -archive \
    -archivedirectory="$ARCHIVE_DIR" \
    -utf8output 2>&1 | tee "$LOG_FILE"
  code=${PIPESTATUS[0]}
  set -e

  if [[ "$code" -eq 0 ]]; then
    break
  fi

  if [[ "$attempt" -lt "$UE_RETRIES" ]]; then
    echo "[build_package] Attempt failed (exit=$code). Retrying in ${UE_RETRY_DELAY_SEC}s..."
    sleep "$UE_RETRY_DELAY_SEC"
  fi
  attempt=$((attempt + 1))
done

if [[ "$code" -ne 0 ]]; then
  echo "[build_package] FAILED after $UE_RETRIES attempt(s). See log: $LOG_FILE" >&2
  exit "$code"
fi

BINARY_PATH="$ARCHIVE_DIR/Linux/$PROJECT_NAME/Binaries/Linux/$PROJECT_NAME"

echo "[build_package] Complete. Output: $ARCHIVE_DIR"
echo "[build_package] Expected binary: $BINARY_PATH"
[[ -x "$BINARY_PATH" ]] && echo "[build_package] Binary exists and is executable." || echo "[build_package] Binary not found at expected path."
