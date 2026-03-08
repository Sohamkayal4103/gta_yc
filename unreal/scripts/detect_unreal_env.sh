#!/usr/bin/env bash
set -euo pipefail

# Detect Unreal Engine installation and Epic source-access readiness.
# Output: human-readable logs + JSON summary.

UE_ROOT=${UE_ROOT:-}
UE_PROJECT=${UE_PROJECT:-}
UE_SOURCE_DIR=${UE_SOURCE_DIR:-$HOME/src/UnrealEngine}
OUT_JSON=${OUT_JSON:-/tmp/unreal_env_detect.json}

hr() { printf '%*s\n' "${COLUMNS:-80}" '' | tr ' ' '-'; }

if [[ -z "$UE_ROOT" ]]; then
  for cand in /opt/UnrealEngine /opt/UnrealEngine-* "$HOME/UnrealEngine" "$UE_SOURCE_DIR"; do
    if [[ -d "$cand/Engine/Build/BatchFiles" ]]; then
      UE_ROOT="$cand"
      break
    fi
  done
fi

ue_found=false
run_uat=""
if [[ -n "$UE_ROOT" && -x "$UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh" ]]; then
  ue_found=true
  run_uat="$UE_ROOT/Engine/Build/BatchFiles/RunUAT.sh"
fi

epic_auth_hint="missing"
for p in "$HOME/.git-credentials" "$HOME/.config/gh/hosts.yml"; do
  if [[ -f "$p" ]] && grep -qi "epicgames\|github.com" "$p"; then
    epic_auth_hint="present"
    break
  fi
done

source_repo_present=false
if [[ -d "$UE_SOURCE_DIR/.git" ]]; then
  source_repo_present=true
fi

can_clone_epic=false
if command -v git >/dev/null 2>&1; then
  set +e
  git ls-remote --heads git@github.com:EpicGames/UnrealEngine.git >/dev/null 2>&1
  ssh_code=$?
  set -e
  if [[ "$ssh_code" -eq 0 ]]; then
    can_clone_epic=true
  fi
fi

project_found=false
if [[ -n "$UE_PROJECT" && -f "$UE_PROJECT" ]]; then
  project_found=true
fi

hr
echo "[detect] Unreal root: ${UE_ROOT:-<not found>}"
echo "[detect] Unreal installed: $ue_found"
echo "[detect] RunUAT: ${run_uat:-<missing>}"
echo "[detect] UE source repo present: $source_repo_present ($UE_SOURCE_DIR)"
echo "[detect] Epic auth hint: $epic_auth_hint"
echo "[detect] Can reach EpicGames/UnrealEngine via SSH: $can_clone_epic"
echo "[detect] UE project path: ${UE_PROJECT:-<unset>}"
echo "[detect] UE project found: $project_found"
hr

export UE_ROOT UE_PROJECT UE_SOURCE_DIR OUT_JSON RUN_UAT_PATH="$run_uat" UE_FOUND="$ue_found" EPIC_AUTH_HINT="$epic_auth_hint" SOURCE_REPO_PRESENT="$source_repo_present" CAN_CLONE_EPIC="$can_clone_epic" PROJECT_FOUND="$project_found"
python3 - <<'PY'
import json
import os


def _to_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}

summary = {
    "ue_root": os.getenv("UE_ROOT") or None,
    "ue_found": _to_bool(os.getenv("UE_FOUND", "false")),
    "run_uat": os.getenv("RUN_UAT_PATH") or None,
    "ue_source_dir": os.getenv("UE_SOURCE_DIR") or None,
    "source_repo_present": _to_bool(os.getenv("SOURCE_REPO_PRESENT", "false")),
    "epic_auth_hint": os.getenv("EPIC_AUTH_HINT") or "missing",
    "can_clone_epic": _to_bool(os.getenv("CAN_CLONE_EPIC", "false")),
    "ue_project": os.getenv("UE_PROJECT") or None,
    "project_found": _to_bool(os.getenv("PROJECT_FOUND", "false")),
}
out_json = os.getenv("OUT_JSON", "/tmp/unreal_env_detect.json")
with open(out_json, "w", encoding="utf-8") as f:
    json.dump(summary, f, indent=2)
print(f"[detect] Wrote summary: {out_json}")
PY
