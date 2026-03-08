'use client';

import { useEffect, useMemo, useState } from 'react';
import { getUnrealSceneBundle, UnrealSceneBundleData } from '@/lib/api';

interface UnrealStreamViewerProps {
  sessionId: string;
  playerUrl?: string;
}

export default function UnrealStreamViewer({ sessionId, playerUrl }: UnrealStreamViewerProps) {
  const [bundle, setBundle] = useState<UnrealSceneBundleData | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getUnrealSceneBundle(sessionId)
      .then(setBundle)
      .catch((e: Error) => setError(e.message));
  }, [sessionId]);

  const resolvedPlayerUrl = useMemo(() => {
    if (playerUrl) return playerUrl;
    return bundle?.streaming.pixel_streaming.player_url || process.env.NEXT_PUBLIC_UE_PLAYER_URL || 'http://127.0.0.1:80';
  }, [bundle, playerUrl]);

  return (
    <div className="relative w-full h-screen bg-black">
      <iframe
        src={resolvedPlayerUrl}
        title="Unreal Pixel Streaming"
        className="w-full h-full border-0"
        allow="autoplay; fullscreen; microphone; camera; clipboard-read; clipboard-write"
      />

      <div className="absolute top-3 left-3 bg-black/60 backdrop-blur-sm rounded px-3 py-2 text-xs text-gray-200 max-w-[36rem]">
        <div className="font-semibold text-white mb-1">Unreal Pixel Streaming</div>
        <div>Session: {sessionId}</div>
        <div>Player: {resolvedPlayerUrl}</div>
        {bundle?.streaming.pixel_streaming.signaling_url && (
          <div>Signaling: {bundle.streaming.pixel_streaming.signaling_url}</div>
        )}
        {bundle?.world_settings?.scalability && (
          <div>Scalability: {bundle.world_settings.scalability}</div>
        )}
        {error && <div className="text-red-300">Bundle error: {error}</div>}
      </div>
    </div>
  );
}
