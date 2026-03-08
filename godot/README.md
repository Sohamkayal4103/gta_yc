# Godot Project (planned)

This directory is reserved for the Godot 4 runtime project.

Planned immediate contents:
- `project.godot`
- `scenes/Main.tscn`
- `scripts/SceneLoader.gd`
- `scripts/HostBridge.gd` for web postMessage bridge

Until Godot is installed in the environment, the Next.js app uses a placeholder web export at:
- `frontend/public/godot/index.html`

Run universe page with:
- Godot runtime (default): `/universe/<sessionId>`
- Three.js fallback: `/universe/<sessionId>?engine=three`
