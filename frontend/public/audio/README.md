# Ambient audio placeholder

`ambient_loop_placeholder.wav` is a locally generated, safe placeholder loop used by the Three.js runtime.

## Replace with custom ambience

1. Add your own loopable file (wav/mp3/ogg) under this folder.
2. Keep duration between 15s and 90s for quick preload.
3. Update `frontend/src/components/AmbientLoop.tsx` default `src` if filename changes.

The runtime starts playback only after user interaction (browser autoplay policy compliant).
