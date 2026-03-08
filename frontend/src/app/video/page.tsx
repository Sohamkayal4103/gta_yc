'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  createRealtimeSegmentationSession,
  createVideoSegmentationSession,
  getVideoSegmentationEvents,
  getVideoSegmentationFrames,
  getVideoSegmentationResult,
  getVideoSegmentationSession,
  SegmentedFrame,
  SessionEvent,
  resolveAssetUrl,
  stopRealtimeSegmentationSession,
  submitSelectedFrames,
  uploadRealtimeFrame,
  VideoSegmentationResult,
  VideoSegmentationSessionStatus,
} from '@/lib/api';

const REFRESH_MS = 1800;

type CaptureMode = 'interval' | 'scene_change';

export default function VideoPipelinePage() {
  const [inputMode, setInputMode] = useState<'upload' | 'live'>('upload');
  const [videoFile, setVideoFile] = useState<File | null>(null);
  const [frameIntervalSec, setFrameIntervalSec] = useState<number>(10);
  const [captureMode, setCaptureMode] = useState<CaptureMode>('interval');
  const [jpegQuality, setJpegQuality] = useState<number>(0.78);
  const [sceneDiffThreshold, setSceneDiffThreshold] = useState<number>(0.08);

  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionInput, setSessionInput] = useState<string>('');
  const [status, setStatus] = useState<VideoSegmentationSessionStatus | null>(null);
  const [frames, setFrames] = useState<SegmentedFrame[]>([]);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [result, setResult] = useState<VideoSegmentationResult | null>(null);
  const [events, setEvents] = useState<SessionEvent[]>([]);
  const [eventCursor, setEventCursor] = useState<number>(0);

  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [cameraLive, setCameraLive] = useState(false);
  const [uploadedFrames, setUploadedFrames] = useState(0);

  const videoRef = useRef<HTMLVideoElement | null>(null);
  const captureCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const diffCanvasRef = useRef<HTMLCanvasElement | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const captureTimerRef = useRef<number | null>(null);
  const frameUploadInFlightRef = useRef(false);
  const prevDiffPixelsRef = useRef<Uint8ClampedArray | null>(null);
  const lastSentTsRef = useRef<number>(0);
  const liveStartTsRef = useRef<number>(0);

  useEffect(() => {
    if (!sessionId) return;

    const interval = setInterval(async () => {
      try {
        const [s, f, e] = await Promise.all([
          getVideoSegmentationSession(sessionId),
          getVideoSegmentationFrames(sessionId),
          getVideoSegmentationEvents(sessionId, eventCursor),
        ]);

        setStatus(s);
        if (s.error) {
          setError(`Session error: ${s.error}`);
        }
        setFrames((f.frames || []).filter((x: SegmentedFrame) => x.status === 'complete'));

        if (e.events?.length) {
          setEvents((prev) => [...prev, ...e.events].slice(-150));
          setEventCursor(e.latest || eventCursor);
        }

        if (s.status === 'complete') {
          const finalResult = await getVideoSegmentationResult(sessionId);
          setResult(finalResult);
          clearInterval(interval);
        }
      } catch {
        // transient polling failures
      }
    }, REFRESH_MS);

    return () => clearInterval(interval);
  }, [sessionId, eventCursor]);

  useEffect(() => {
    return () => {
      stopLocalCamera();
    };
  }, []);

  const selectedIds = useMemo(() => Object.keys(selected).filter((id) => selected[id]), [selected]);

  const runtimeMeta = useMemo(() => {
    const latestWithPayload = [...events].reverse().find((evt) => evt.payload && Object.keys(evt.payload).length > 0)?.payload || {};
    return {
      overshootMode:
        status?.overshoot_mode ||
        result?.models?.overshoot_mode ||
        (latestWithPayload.overshoot_mode as string | undefined) ||
        'mock',
      overshootAdapter:
        status?.overshoot_adapter ||
        result?.models?.overshoot_adapter ||
        (latestWithPayload.overshoot_adapter as string | undefined) ||
        'generic_v1',
      geminiModel:
        status?.gemini_model ||
        result?.models?.gemini ||
        (latestWithPayload.gemini_model as string | undefined) ||
        'gemini-2.5-pro',
    };
  }, [status, result, events]);

  const timeline = useMemo(() => {
    const hasGeminiEvent = events.some((evt) => evt.type === 'gemini_scene_generation' || evt.type === 'gemini_scene_ready');
    const stage = status?.stage || '';
    const done = status?.status === 'complete';

    return [
      {
        key: 'overshoot',
        title: 'Overshoot segmentation',
        subtitle: `mode=${runtimeMeta.overshootMode} | adapter=${runtimeMeta.overshootAdapter}`,
        active: ['frame_extraction', 'segmentation', 'live_capture', 'live_segmentation'].includes(stage),
        complete:
          ['selection', 'gemini_scene_generation', 'complete'].includes(stage) ||
          status?.status === 'ready_for_selection' ||
          done,
      },
      {
        key: 'gemini',
        title: 'Gemini scene generation',
        subtitle: `model=${runtimeMeta.geminiModel}`,
        active: stage === 'gemini_scene_generation' || hasGeminiEvent,
        complete: done,
      },
      {
        key: 'runtime',
        title: 'Playable runtime routing',
        subtitle: done
          ? result?.play_routes?.unreal_stream_available
            ? 'Three + Unreal stream available'
            : 'Three runtime ready'
          : 'Waiting for generated scene',
        active: done,
        complete: done,
      },
    ];
  }, [status, events, runtimeMeta]);

  const resetSessionState = () => {
    setSessionId(null);
    setStatus(null);
    setFrames([]);
    setSelected({});
    setResult(null);
    setEvents([]);
    setEventCursor(0);
    setUploadedFrames(0);
  };

  const loadExistingSession = async () => {
    const sid = sessionInput.trim();
    if (!sid) return;
    setBusy(true);
    setError(null);
    try {
      const [s, f, e] = await Promise.all([
        getVideoSegmentationSession(sid),
        getVideoSegmentationFrames(sid),
        getVideoSegmentationEvents(sid, 0),
      ]);
      setSessionId(sid);
      setStatus(s);
      setFrames((f.frames || []).filter((x: SegmentedFrame) => x.status === 'complete'));
      setEvents(e.events || []);
      setEventCursor(e.latest || 0);
      if (s.status === 'complete') {
        const finalResult = await getVideoSegmentationResult(sid);
        setResult(finalResult);
      }
    } catch (e: any) {
      setError(e.message || 'Failed to load session');
    } finally {
      setBusy(false);
    }
  };

  const startUploadSession = async () => {
    if (!videoFile) return;
    setBusy(true);
    setError(null);
    resetSessionState();

    try {
      const res = await createVideoSegmentationSession(videoFile, frameIntervalSec);
      setSessionId(res.session_id);
    } catch (e: any) {
      setError(e.message || 'Failed to create session');
    } finally {
      setBusy(false);
    }
  };

  const startCameraSession = async () => {
    setBusy(true);
    setError(null);
    resetSessionState();

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });

      mediaStreamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }

      const session = await createRealtimeSegmentationSession(frameIntervalSec, captureMode);
      setSessionId(session.session_id);
      setStatus(session);
      setEventCursor(0);
      setCameraLive(true);
      liveStartTsRef.current = Date.now();

      captureTimerRef.current = window.setInterval(() => {
        captureAndUploadFrame(session.session_id).catch(() => {
          // status polling + events will display failures
        });
      }, Math.max(500, frameIntervalSec * 1000));
    } catch (e: any) {
      setError(e.message || 'Failed to start camera session');
      stopLocalCamera();
    } finally {
      setBusy(false);
    }
  };

  const stopLocalCamera = () => {
    if (captureTimerRef.current) {
      window.clearInterval(captureTimerRef.current);
      captureTimerRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setCameraLive(false);
    frameUploadInFlightRef.current = false;
    prevDiffPixelsRef.current = null;
  };

  const stopCameraSession = async () => {
    const sid = sessionId;
    stopLocalCamera();
    if (!sid) return;

    try {
      setBusy(true);
      const latest = await stopRealtimeSegmentationSession(sid);
      setStatus(latest);
    } catch (e: any) {
      setError(e.message || 'Failed to stop realtime session');
    } finally {
      setBusy(false);
    }
  };

  const shouldUploadBySceneDiff = (): boolean => {
    if (captureMode !== 'scene_change') return true;

    const sourceVideo = videoRef.current;
    const diffCanvas = diffCanvasRef.current;
    if (!sourceVideo || !diffCanvas) return true;

    const w = 64;
    const h = 36;
    diffCanvas.width = w;
    diffCanvas.height = h;
    const ctx = diffCanvas.getContext('2d', { willReadFrequently: true });
    if (!ctx) return true;

    ctx.drawImage(sourceVideo, 0, 0, w, h);
    const pixels = ctx.getImageData(0, 0, w, h).data;

    const prev = prevDiffPixelsRef.current;
    prevDiffPixelsRef.current = new Uint8ClampedArray(pixels);

    if (!prev) return true;

    let diff = 0;
    for (let i = 0; i < pixels.length; i += 4) {
      diff += Math.abs(pixels[i] - prev[i]);
      diff += Math.abs(pixels[i + 1] - prev[i + 1]);
      diff += Math.abs(pixels[i + 2] - prev[i + 2]);
    }

    const normalized = diff / (w * h * 3 * 255);
    const now = Date.now();
    const maxGapMs = Math.max(3000, frameIntervalSec * 3000);
    const elapsedSinceSend = now - lastSentTsRef.current;
    return normalized >= sceneDiffThreshold || elapsedSinceSend >= maxGapMs;
  };

  const captureAndUploadFrame = async (sid: string) => {
    if (frameUploadInFlightRef.current) return;
    const sourceVideo = videoRef.current;
    const canvas = captureCanvasRef.current;
    if (!sourceVideo || !canvas || sourceVideo.readyState < 2) return;
    if (!shouldUploadBySceneDiff()) return;

    frameUploadInFlightRef.current = true;
    try {
      const width = sourceVideo.videoWidth || 1280;
      const height = sourceVideo.videoHeight || 720;
      canvas.width = width;
      canvas.height = height;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      ctx.drawImage(sourceVideo, 0, 0, width, height);

      const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, 'image/jpeg', jpegQuality));
      if (!blob) return;

      const timestampSec = (Date.now() - liveStartTsRef.current) / 1000;

      let attempt = 0;
      let lastErr: any = null;
      while (attempt < 3) {
        try {
          await uploadRealtimeFrame(sid, blob, timestampSec);
          setUploadedFrames((v) => v + 1);
          lastSentTsRef.current = Date.now();
          break;
        } catch (err) {
          lastErr = err;
          attempt += 1;
          if (attempt < 3) {
            await new Promise((r) => setTimeout(r, 400 * attempt));
          }
        }
      }

      if (attempt >= 3 && lastErr) {
        throw lastErr;
      }
    } finally {
      frameUploadInFlightRef.current = false;
    }
  };

  const generateScene = async () => {
    if (!sessionId || selectedIds.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const sceneRes = await submitSelectedFrames(sessionId, selectedIds);
      setResult(sceneRes.result);
      const latest = await getVideoSegmentationSession(sessionId);
      setStatus(latest);
    } catch (e: any) {
      setError(e.message || 'Failed to generate scene');
    } finally {
      setBusy(false);
    }
  };

  const toggleSelection = (frameId: string) => {
    setSelected((prev) => ({ ...prev, [frameId]: !prev[frameId] }));
  };

  return (
    <main className="min-h-screen p-6 md:p-10 bg-black text-white">
      <div className="max-w-6xl mx-auto space-y-6">
        <header className="space-y-2">
          <h1 className="text-3xl md:text-4xl font-bold bg-gradient-to-r from-cyan-400 to-purple-500 bg-clip-text text-transparent">
            Video/Camera → Segmentation → Unreal Scene
          </h1>
          <p className="text-gray-400 text-sm md:text-base">
            Upload a video OR turn on laptop camera for near-realtime keyframe segmentation. Select best segmented
            keyframes and generate a mission-ready Unreal scene bundle.
          </p>
        </header>

        <section className="bg-gray-900/70 border border-gray-800 rounded-xl p-4 md:p-6 space-y-4">
          <div className="grid md:grid-cols-[1fr_auto] gap-2 items-end">
            <label className="space-y-1">
              <span className="text-xs text-gray-400">Already have a Session ID? Load it here</span>
              <input
                value={sessionInput}
                onChange={(e) => setSessionInput(e.target.value)}
                placeholder="e73476aacc"
                className="w-full rounded-md bg-gray-800 border border-gray-700 px-3 py-2 text-sm"
              />
            </label>
            <button
              onClick={loadExistingSession}
              disabled={busy || !sessionInput.trim()}
              className="px-4 py-2 rounded-md bg-indigo-600 hover:bg-indigo-500 disabled:bg-gray-700 disabled:cursor-not-allowed"
            >
              Load Session
            </button>
          </div>

          <div className="flex gap-3 flex-wrap">
            <button
              onClick={() => setInputMode('upload')}
              className={`px-4 py-2 rounded-md border ${
                inputMode === 'upload' ? 'bg-cyan-600 border-cyan-400' : 'bg-gray-900 border-gray-700'
              }`}
            >
              Upload video
            </button>
            <button
              onClick={() => setInputMode('live')}
              className={`px-4 py-2 rounded-md border ${
                inputMode === 'live' ? 'bg-purple-600 border-purple-400' : 'bg-gray-900 border-gray-700'
              }`}
            >
              Live laptop camera
            </button>
          </div>

          {inputMode === 'upload' ? (
            <div className="grid md:grid-cols-3 gap-4">
              <label className="space-y-2">
                <span className="text-sm text-gray-300">Upload video</span>
                <input
                  type="file"
                  accept="video/*"
                  onChange={(e) => setVideoFile(e.target.files?.[0] || null)}
                  className="block w-full text-sm text-gray-200 file:mr-3 file:px-3 file:py-2 file:rounded-md file:border-0 file:bg-cyan-600 file:text-white"
                />
              </label>

              <label className="space-y-2">
                <span className="text-sm text-gray-300">Frame interval (sec)</span>
                <input
                  type="number"
                  min={1}
                  value={frameIntervalSec}
                  onChange={(e) => setFrameIntervalSec(Math.max(1, Number(e.target.value) || 10))}
                  className="w-full rounded-md bg-gray-800 border border-gray-700 px-3 py-2"
                />
              </label>

              <div className="flex items-end">
                <button
                  onClick={startUploadSession}
                  disabled={!videoFile || busy}
                  className="w-full md:w-auto px-6 py-2.5 rounded-md bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-700 disabled:cursor-not-allowed"
                >
                  {busy ? 'Starting...' : 'Start Upload Segmentation'}
                </button>
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid md:grid-cols-4 gap-3">
                <label className="space-y-2">
                  <span className="text-sm text-gray-300">Capture interval (sec)</span>
                  <input
                    type="number"
                    min={1}
                    value={frameIntervalSec}
                    onChange={(e) => setFrameIntervalSec(Math.max(1, Number(e.target.value) || 10))}
                    className="w-full rounded-md bg-gray-800 border border-gray-700 px-3 py-2"
                  />
                </label>

                <label className="space-y-2">
                  <span className="text-sm text-gray-300">Capture mode</span>
                  <select
                    value={captureMode}
                    onChange={(e) => setCaptureMode(e.target.value as CaptureMode)}
                    className="w-full rounded-md bg-gray-800 border border-gray-700 px-3 py-2"
                  >
                    <option value="interval">Periodic keyframes</option>
                    <option value="scene_change">Scene-change aware</option>
                  </select>
                </label>

                <label className="space-y-2">
                  <span className="text-sm text-gray-300">JPEG quality ({jpegQuality.toFixed(2)})</span>
                  <input
                    type="range"
                    min={0.4}
                    max={0.95}
                    step={0.05}
                    value={jpegQuality}
                    onChange={(e) => setJpegQuality(Number(e.target.value))}
                    className="w-full"
                  />
                </label>

                <label className="space-y-2">
                  <span className="text-sm text-gray-300">Scene threshold ({sceneDiffThreshold.toFixed(2)})</span>
                  <input
                    type="range"
                    min={0.02}
                    max={0.2}
                    step={0.01}
                    value={sceneDiffThreshold}
                    onChange={(e) => setSceneDiffThreshold(Number(e.target.value))}
                    className="w-full"
                  />
                </label>
              </div>

              <div className="flex gap-3 flex-wrap">
                <button
                  onClick={startCameraSession}
                  disabled={busy || cameraLive}
                  className="px-5 py-2.5 rounded-md bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 disabled:cursor-not-allowed"
                >
                  {cameraLive ? 'Camera Running' : busy ? 'Starting...' : 'Start Camera Capture'}
                </button>
                <button
                  onClick={stopCameraSession}
                  disabled={!cameraLive || busy}
                  className="px-5 py-2.5 rounded-md bg-rose-600 hover:bg-rose-500 disabled:bg-gray-700 disabled:cursor-not-allowed"
                >
                  Stop & Finalize Capture
                </button>
                <div className="text-xs text-gray-400 self-center">Uploaded keyframes: {uploadedFrames}</div>
              </div>

              <div className="rounded-lg overflow-hidden border border-gray-800 bg-black max-w-2xl">
                <video ref={videoRef} autoPlay muted playsInline className="w-full h-72 object-cover" />
              </div>
              <canvas ref={captureCanvasRef} className="hidden" />
              <canvas ref={diffCanvasRef} className="hidden" />
            </div>
          )}

          {error && <p className="text-red-400 text-sm">{error}</p>}

          {status && (
            <div className="space-y-3">
              <div className="text-sm text-gray-300">
                {status.stage} — {status.message}
              </div>
              <div className="w-full h-2 bg-gray-800 rounded-full overflow-hidden">
                <div className="h-2 bg-gradient-to-r from-cyan-500 to-purple-500" style={{ width: `${status.progress}%` }} />
              </div>
              <div className="text-xs text-gray-500">
                {status.frames_segmented}/{status.frames_total} frames segmented
              </div>

              <div className="grid md:grid-cols-3 gap-2">
                {timeline.map((item) => {
                  const tone = item.complete
                    ? 'border-emerald-600/60 bg-emerald-950/30 text-emerald-300'
                    : item.active
                      ? 'border-cyan-500/60 bg-cyan-950/20 text-cyan-200'
                      : 'border-gray-700 bg-gray-900/50 text-gray-400';
                  return (
                    <div key={item.key} className={`rounded-md border px-3 py-2 text-xs ${tone}`}>
                      <div className="font-semibold">{item.title}</div>
                      <div className="opacity-90">{item.subtitle}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </section>

        {events.length > 0 && (
          <section className="bg-gray-900/50 border border-gray-800 rounded-xl p-4">
            <h2 className="text-sm font-semibold text-gray-300 mb-2">Live status events</h2>
            <div className="max-h-44 overflow-auto space-y-1 text-xs text-gray-400 font-mono">
              {events.slice(-25).map((evt) => (
                <div key={evt.seq}>[{evt.seq}] {evt.type}: {evt.message}</div>
              ))}
            </div>
          </section>
        )}

        {frames.length > 0 && (
          <section className="space-y-4">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <h2 className="text-xl font-semibold">Choose Segmented Keyframes</h2>
              <button
                onClick={generateScene}
                disabled={selectedIds.length === 0 || busy}
                className="px-5 py-2 rounded-md bg-purple-600 hover:bg-purple-500 disabled:bg-gray-700 disabled:cursor-not-allowed"
              >
                {busy ? 'Generating...' : `Generate Scene from ${selectedIds.length} frame(s)`}
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {frames.map((frame) => (
                <article key={frame.frame_id} className="border border-gray-800 rounded-lg overflow-hidden bg-gray-950">
                  <div className="relative">
                    <img
                      src={resolveAssetUrl(frame.overlay_url) || resolveAssetUrl(frame.frame_url) || undefined}
                      alt={frame.frame_id}
                      className="w-full h-52 object-cover"
                      onError={(evt) => {
                        const fallback = resolveAssetUrl(frame.frame_url);
                        if (fallback && evt.currentTarget.src !== fallback) {
                          evt.currentTarget.src = fallback;
                        }
                      }}
                    />
                    <label className="absolute top-2 left-2 bg-black/70 px-2 py-1 rounded text-xs">
                      <input
                        type="checkbox"
                        checked={!!selected[frame.frame_id]}
                        onChange={() => toggleSelection(frame.frame_id)}
                        className="mr-2"
                      />
                      select
                    </label>
                  </div>
                  <div className="p-3 space-y-2 text-xs text-gray-300">
                    <div className="flex justify-between">
                      <span>{frame.frame_id}</span>
                      <span>t={frame.timestamp_sec.toFixed(1)}s</span>
                    </div>
                    <div className="text-gray-400">Objects: {frame.objects?.length || 0}</div>
                    <div className="flex flex-wrap gap-1">
                      {(frame.objects || []).slice(0, 6).map((obj) => (
                        <span key={obj.id} className="px-2 py-0.5 rounded bg-gray-800 border border-gray-700">
                          {obj.label} {obj.confidence.toFixed(2)}
                        </span>
                      ))}
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
        )}

        {result && (
          <section className="bg-emerald-900/15 border border-emerald-700/40 rounded-xl p-5 space-y-3">
            <h2 className="text-xl font-semibold text-emerald-300">Mission-ready Scene Generated</h2>
            <p className="text-sm text-gray-200">
              Scene ID: <span className="font-mono">{result.scene_id}</span>
            </p>
            <p className="text-sm text-gray-300">Missions: {result.bundle?.missions?.length || 0}</p>
            <p className="text-sm text-gray-300">Map: {result.bundle?.map_name}</p>
            <div className="text-xs text-gray-400 space-y-1">
              <div>Includes mandatory hidden Mac mini objective in the mission chain.</div>
              <div>
                Gemini: {runtimeMeta.geminiModel} | Overshoot: {runtimeMeta.overshootMode}/{runtimeMeta.overshootAdapter}
              </div>
            </div>

            <div className="flex flex-wrap gap-3 pt-1">
              <a
                href={result.play_routes?.three_url || `/universe/${result.session_id}?engine=three`}
                className="inline-flex items-center justify-center px-6 py-3 rounded-md bg-emerald-500 hover:bg-emerald-400 text-black font-bold text-base"
              >
                ▶ Play Game
              </a>

              {result.play_routes?.unreal_stream_available && result.play_routes?.unreal_url && (
                <a
                  href={result.play_routes.unreal_url}
                  className="inline-flex items-center justify-center px-5 py-3 rounded-md bg-indigo-500 hover:bg-indigo-400 text-white font-semibold"
                >
                  Play in Unreal Stream
                </a>
              )}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
