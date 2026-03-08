#!/usr/bin/env bash
set -euo pipefail

# End-to-end Unreal detect/build/package orchestrator.
# Safe by default: does not clone Epic repo unless AUTO_CLONE_EPIC=1.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(cd "$SCRIPT_DIR/../.." && pwd)
LOG_ROOT=${UE_AUTOBUILD_LOG_ROOT:-"$PROJECT_ROOT/unreal/logs"}
mkdir -p "$LOG_ROOT"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
RUN_LOG="$LOG_ROOT/auto_build_${STAMP}.log"
DETECT_JSON="$LOG_ROOT/detect_${STAMP}.json"
BLOCKERS_MD=${UNREAL_BLOCKERS_FILE:-"$PROJECT_ROOT/UNREAL_BUILD_BLOCKERS.md"}

AUTO_CLONE_EPIC=${AUTO_CLONE_EPIC:-0}
UE_SOURCE_DIR=${UE_SOURCE_DIR:-$HOME/src/UnrealEngine}

exec > >(tee -a "$RUN_LOG") 2>&1

echo "[auto-build] Started at $(date -u +%FT%TZ)"
echo "[auto-build] Logs: $RUN_LOG"
echo "[auto-build] Detect summary: $DETECT_JSON"

OUT_JSON="$DETECT_JSON" "$SCRIPT_DIR/detect_unreal_env.sh" || true

if [[ ! -f "$DETECT_JSON" ]]; then
  echo "[auto-build] Detection summary missing."
  echo "- Detection script failed before producing summary." > "$BLOCKERS_MD"
  exit 1
fi

readarray -t DETECT_LINES < <(python3 - <<PY
import json
with open("$DETECT_JSON", "r", encoding="utf-8") as f:
    d = json.load(f)
for key in ["ue_root", "ue_found", "run_uat", "source_repo_present", "can_clone_epic", "ue_project", "project_found"]:
    print(f"{key}={d.get(key)}")
PY
)

declare -A DETECT
for line in "${DETECT_LINES[@]}"; do
  key=${line%%=*}
  val=${line#*=}
  DETECT[$key]="$val"
done

ue_root="${DETECT[ue_root]}"
ue_found="${DETECT[ue_found]}"
source_repo_present="${DETECT[source_repo_present]}"
can_clone_epic="${DETECT[can_clone_epic]}"
ue_project="${DETECT[ue_project]}"
project_found="${DETECT[project_found]}"

blockers=()

normalize_bool() {
  [[ "${1,,}" == "true" ]]
}

if ! normalize_bool "$ue_found"; then
  echo "[auto-build] Unreal binary/source root not detected."

  if normalize_bool "$source_repo_present"; then
    if [[ -x "$UE_SOURCE_DIR/Engine/Build/BatchFiles/RunUAT.sh" ]]; then
      ue_root="$UE_SOURCE_DIR"
      ue_found="true"
      echo "[auto-build] Using UE source directory: $ue_root"
    else
      blockers+=("Unreal source repo exists at $UE_SOURCE_DIR but engine binaries are not built yet. Run ./Setup.sh && ./GenerateProjectFiles.sh && make from that repo.")
    fi
  elif normalize_bool "$can_clone_epic" && [[ "$AUTO_CLONE_EPIC" == "1" ]]; then
    echo "[auto-build] Attempting Epic clone into $UE_SOURCE_DIR"
    mkdir -p "$(dirname "$UE_SOURCE_DIR")"
    git clone --depth 1 git@github.com:EpicGames/UnrealEngine.git "$UE_SOURCE_DIR" || true
    if [[ -x "$UE_SOURCE_DIR/Engine/Build/BatchFiles/RunUAT.sh" ]]; then
      ue_root="$UE_SOURCE_DIR"
      ue_found="true"
    else
      blockers+=("Epic source clone attempted but repository not available/accessible. Confirm Epic↔GitHub access and rerun with AUTO_CLONE_EPIC=1.")
    fi
  else
    blockers+=("Unreal Engine not found and Epic clone is unavailable. Required action: link GitHub account in Epic dashboard, accept Unreal EULA, then grant this host git access to git@github.com:EpicGames/UnrealEngine.git.")
  fi
fi

if normalize_bool "$ue_found"; then
  if ! normalize_bool "$project_found"; then
    if [[ -z "${UE_PROJECT:-}" ]]; then
      blockers+=("UE_PROJECT is not set. Provide absolute path to .uproject and rerun auto_build_and_package.sh.")
    elif [[ ! -f "${UE_PROJECT}" ]]; then
      blockers+=("UE_PROJECT is set but file not found: ${UE_PROJECT}")
    fi
  fi
fi

if normalize_bool "$ue_found" && [[ -n "${UE_PROJECT:-}" && -f "${UE_PROJECT}" ]]; then
  export UE_ROOT="$ue_root"
  echo "[auto-build] Running package build with UE_ROOT=$UE_ROOT UE_PROJECT=$UE_PROJECT"
  if ! "$SCRIPT_DIR/build_package.sh"; then
    blockers+=("RunUAT BuildCookRun failed. See detailed logs under unreal/logs and project Saved/Logs.")
  fi
fi

if [[ ${#blockers[@]} -gt 0 ]]; then
  {
    echo "# Unreal Build Blockers"
    echo
    echo "Generated: $(date -u +%FT%TZ)"
    echo
    echo "## What was attempted"
    echo "- Environment detection via unreal/scripts/detect_unreal_env.sh"
    echo "- Optional source clone/build path checks"
    echo "- Packaging via unreal/scripts/build_package.sh when prerequisites were available"
    echo
    echo "## Blockers"
    for blocker in "${blockers[@]}"; do
      echo "- $blocker"
    done
    echo
    echo "## Log references"
    echo "- Auto build log: $RUN_LOG"
    echo "- Detection JSON: $DETECT_JSON"
  } > "$BLOCKERS_MD"

  echo "[auto-build] Blockers written: $BLOCKERS_MD"
  exit 2
fi

if [[ -f "$BLOCKERS_MD" ]]; then
  rm -f "$BLOCKERS_MD"
fi

echo "[auto-build] Unreal build/package flow completed without blockers."
