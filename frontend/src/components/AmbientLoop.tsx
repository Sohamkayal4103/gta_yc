'use client';

import { useEffect, useRef, useState } from 'react';

interface AmbientLoopProps {
  src?: string;
}

export default function AmbientLoop({ src = '/audio/ambient_loop_placeholder.wav' }: AmbientLoopProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [enabled, setEnabled] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startLoop = async () => {
    if (!audioRef.current) return;
    try {
      await audioRef.current.play();
      setEnabled(true);
      setError(null);
    } catch {
      setError('Tap once to start ambient audio');
    }
  };

  useEffect(() => {
    const audio = new Audio(src);
    audio.loop = true;
    audio.volume = 0.24;
    audio.preload = 'auto';
    audioRef.current = audio;

    const onFirstInteraction = () => {
      if (!enabled) {
        startLoop();
      }
    };

    window.addEventListener('pointerdown', onFirstInteraction, { once: true });

    return () => {
      window.removeEventListener('pointerdown', onFirstInteraction);
      audio.pause();
      audioRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src]);

  return (
    <div className="absolute top-4 right-4 z-20">
      {!enabled ? (
        <button
          onClick={startLoop}
          className="px-3 py-1.5 rounded-md bg-black/65 border border-white/20 text-xs text-white hover:bg-black/80"
        >
          Enable ambient audio
        </button>
      ) : (
        <div className="px-3 py-1.5 rounded-md bg-black/60 border border-emerald-500/30 text-xs text-emerald-300">
          Ambient audio: ON
        </div>
      )}
      {error && <div className="mt-1 text-[11px] text-amber-300 text-right">{error}</div>}
    </div>
  );
}
