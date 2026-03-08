# Unreal Runtime Integration (Scaffolding)

This folder adds an **Unreal-first runtime path** while keeping existing Godot + Three.js paths untouched.

## What is included

- Host setup script: `scripts/setup_prereqs.sh`
- Environment detection script: `scripts/detect_unreal_env.sh`
- End-to-end auto build/package script: `scripts/auto_build_and_package.sh`
- Package/build script: `scripts/build_package.sh`
- High-quality local run script: `scripts/run_high_quality.sh`
- Pixel Streaming signaling script: `scripts/start_pixel_streaming_infra.sh`
- Pixel Streaming app launch script: `scripts/launch_pixel_streaming_app.sh`
- Stack convenience launcher: `scripts/run_pixel_streaming_stack.sh`
- Diagnostics: `scripts/diagnostics.sh`

## Backend Unreal bundle APIs

- `GET /api/universe/{session_id}/bundle`
- `GET /api/universe/{session_id}/asset-manifest`
- `GET /api/universe/{session_id}/unreal/scene-bundle`

The Unreal scene bundle contains:
- scene payload
- asset manifest placeholders (for UE content mapping)
- pixel streaming URLs
- world settings defaults (`nanite`, `lumen`, ray tracing, cinematic scalability)

## Frontend Unreal pages

- `/unreal` — connect form (session + player URL)
- `/unreal/{sessionId}` — open Pixel Streaming player in-page
- `/universe/{sessionId}?engine=unreal` — runtime switch from existing universe route

## Fast start

```bash
# 1) On server
sudo ./unreal/scripts/setup_prereqs.sh
./unreal/scripts/diagnostics.sh

# 2) Detect environment + attempt end-to-end build/package
UE_PROJECT=/srv/MyGame/MyGame.uproject \
./unreal/scripts/auto_build_and_package.sh

# (optional) direct package call when UE_ROOT is already known
UE_ROOT=/opt/UnrealEngine-5.3 \
UE_PROJECT=/srv/MyGame/MyGame.uproject \
./unreal/scripts/build_package.sh

# 3) Launch Pixel Streaming infra + app
PS_INFRA_ROOT=/srv/PixelStreamingInfrastructure \
UE_APP_BIN=/srv/builds/MyGame/Binaries/Linux/MyGame \
UE_SIGNALING_URL=ws://127.0.0.1:8888 \
./unreal/scripts/run_pixel_streaming_stack.sh
```

Then on laptop browser:
- Open `http://<server-ip>/unreal/<sessionId>?playerUrl=http://<server-ip>:80`
