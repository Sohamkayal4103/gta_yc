'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

interface GodotUniverseViewerProps {
  sessionId: string;
  bundleUrl?: string;
}

export default function GodotUniverseViewer({
  sessionId,
  bundleUrl,
}: GodotUniverseViewerProps) {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [loaded, setLoaded] = useState(false);

  const runtimeBundleUrl = useMemo(
    () => bundleUrl ?? `/api/universe/${sessionId}/bundle`,
    [bundleUrl, sessionId],
  );

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      if (!event?.data || typeof event.data !== 'object') return;
      const payload = event.data as { type?: string; status?: string; message?: string };
      if (payload.type === 'godot:ready') {
        setLoaded(true);
        iframeRef.current?.contentWindow?.postMessage(
          {
            type: 'host:init',
            payload: {
              sessionId,
              sceneBundleUrl: runtimeBundleUrl,
            },
          },
          '*',
        );
      }
    };

    window.addEventListener('message', onMessage);
    return () => window.removeEventListener('message', onMessage);
  }, [runtimeBundleUrl, sessionId]);

  return (
    <div className="relative w-full h-screen bg-black">
      {!loaded && (
        <div className="absolute inset-0 z-10 flex items-center justify-center">
          <p className="text-gray-300 text-sm">Loading Godot runtime…</p>
        </div>
      )}

      <iframe
        ref={iframeRef}
        src="/godot/index.html"
        title="Universe Runtime"
        className="w-full h-full border-0"
        allow="fullscreen; autoplay; clipboard-read; clipboard-write"
      />

      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-black/50 backdrop-blur-sm px-4 py-1.5 rounded-lg text-xs text-gray-400 pointer-events-none select-none">
        Godot Web Runtime · Session {sessionId}
      </div>
    </div>
  );
}
