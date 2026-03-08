# GTA YiceCity

GTA YiceCity is an AI-assisted 3D scene generation and playable runtime project.

<p align="center">
  <img src="README_assets/yc_front.png" alt="Front reference image used to generate the universe" width="31%" />
  <img src="README_assets/yc_left.png" alt="Left reference image used to generate the universe" width="31%" />
  <img src="README_assets/yc_right.png" alt="Right reference image used to generate the universe" width="31%" />
</p>

<p align="center">
  <em>Reference images captured from the real space and used to generate the final universe.</em>
</p>

<p align="center">
  <video src="README_assets/final_video.mp4" controls width="920">
    Your Markdown viewer does not support embedded video. Open
    <a href="README_assets/final_video.mp4">the MP4 demo</a>.
  </video>
</p>

<p align="center">
  <em>Final generated universe demo video.</em>
</p>

<p align="center">
  <a href="https://youtu.be/CIWD4ODJzgs?si=Iv-pkZyjgrykkwln">
    <img
      src="https://img.youtube.com/vi/CIWD4ODJzgs/hqdefault.jpg"
      alt="Watch the GTA YiceCity demo on YouTube"
      width="920"
    />
  </a>
</p>

## What this project does

1. Accepts video or live camera input.
2. Extracts key frames on the server.
3. Runs segmentation through **Overshoot** for object understanding and preview overlays.
4. Sends data to **Gemini** for scene parameter generation:
   - raw selected images
   - Overshoot segmentation-derived context/objects (scene understanding signals)
5. Produces a mission-ready scene bundle (environment, objects, people/NPC context, interactions, mission goals).
6. Loads and plays the generated scene in browser runtime (current stable path: Three.js runtime).

---

## Architecture (high level)

- **Frontend (Next.js)**
  - Upload/live capture UI
  - Segmentation preview + frame selection
  - Scene generation status + play flow

- **Backend (FastAPI/Python)**
  - Frame extraction + session orchestration
  - Overshoot segmentation pipeline
  - Gemini scene generation pipeline
  - Bundle + mission output endpoints

- **Runtime**
  - Browser-playable scene route (`/universe/<sessionId>?engine=three`)
  - Unreal-compatible bundle/export scaffolding is included for future full UE runtime path

---

## Prerequisites

- Linux server (Ubuntu/Debian recommended)
- Node.js 20+ (tested with Node 22)
- npm
- Python 3.10+
- `ffmpeg` + `ffprobe`

Install system packages:

```bash
sudo apt update
sudo apt install -y ffmpeg python3 python3-pip nodejs npm
```

---

## Environment setup

Create `.env` in repo root (`reality-to-videogame/.env`):

```env
GEMINI_API_KEY=your_gemini_api_key
GEMINI_MODEL=gemini-2.5-pro

OVERSHOOT_API_KEY=your_overshoot_api_key
OVERSHOOT_BASE_URL=https://api.overshoot.ai
OVERSHOOT_SEGMENT_PATH=/v1/segment
OVERSHOOT_ADAPTER=generic_v1
OVERSHOOT_TIMEOUT_SEC=45
OVERSHOOT_MAX_RETRIES=3
OVERSHOOT_MOCK_MODE=false
OVERSHOOT_MOCK_ON_ERROR=true

REALTIME_MAX_UPLOAD_MB=8
```

> For local development without live Overshoot credentials, set `OVERSHOOT_MOCK_MODE=true`.

---

## Install dependencies

### Backend

```bash
cd backend
python3 -m pip install -r requirements.txt
cd ..
```

### Frontend

```bash
cd frontend
npm install
cd ..
```

---

## Run on any server (general, non-k8s)

From project root:

### 1) Start backend

```bash
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 2) Start frontend (recommended stable mode)

```bash
cd frontend
npm run build
npm run start:prod
```

(Serves frontend on `0.0.0.0:3000`)

---

## Usage flow

1. Open `http://<SERVER_IP>:3000/video`
2. Upload video or use live camera mode.
3. Wait for Overshoot segmentation previews.
4. Select good frames.
5. Click **Generate Scene**.
6. Click **Play Game**.

Direct play URL pattern:

```text
http://<SERVER_IP>:3000/universe/<SESSION_ID>?engine=three
```

---

## Health checks

- Backend health: `http://<SERVER_IP>:8000/api/health`
- Frontend health: `http://<SERVER_IP>:3000/healthz`

---

## Notes

- Unreal full runtime/streaming path is scaffolded, but browser-stable gameplay path currently uses Three runtime.
- Mission flow includes objective progression and completion states.
- If scene generation fails, inspect session/event endpoints under `/api/video-segmentation/...`.
