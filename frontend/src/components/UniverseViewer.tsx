'use client';

import { useCallback, useRef, useState } from 'react';
import { Canvas } from '@react-three/fiber';
import SceneBuilder from '@/three/SceneBuilder';
import SceneErrorBoundary from './SceneErrorBoundary';
import { InteractionPrompt, ActiveInteraction } from '@/three/ThirdPersonController';
import { Mission } from '@/lib/api';
import MissionHUD from './MissionHUD';
import GodotUniverseViewer from './GodotUniverseViewer';
import UnrealStreamViewer from './UnrealStreamViewer';
import AmbientLoop from './AmbientLoop';

interface UniverseViewerProps {
  sessionId: string;
  engine?: 'godot' | 'three' | 'unreal';
  unrealPlayerUrl?: string;
}

function ThreeUniverseViewer({ sessionId }: { sessionId: string }) {
  const [commentary, setCommentary] = useState<string[]>([]);
  const [interactionPrompt, setInteractionPrompt] = useState<InteractionPrompt | null>(null);
  const [activeInteraction, setActiveInteraction] = useState<ActiveInteraction | null>(null);
  const [missions, setMissions] = useState<Mission[]>([]);
  const [completedMission, setCompletedMission] = useState<Mission | null>(null);
  const [sceneLoading, setSceneLoading] = useState(true);
  const [sceneError, setSceneError] = useState<string | null>(null);
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const handleCommentary = useCallback((lines: string[]) => {
    setCommentary(lines);
    if (fadeTimerRef.current) clearTimeout(fadeTimerRef.current);
    fadeTimerRef.current = setTimeout(() => setCommentary([]), 3000);
  }, []);

  const isActive = !!activeInteraction;

  return (
    <div className="relative w-full h-screen">
      <SceneErrorBoundary>
        <Canvas
          shadows
          camera={{ fov: 60, near: 0.1, far: 1000, position: [0, 3, 5] }}
          gl={{ antialias: true, toneMapping: 3 }}
        >
          <SceneBuilder
            sessionId={sessionId}
            onCommentary={handleCommentary}
            onInteractionPrompt={setInteractionPrompt}
            onActiveInteraction={setActiveInteraction}
            onMissionsUpdate={setMissions}
            onMissionCompleted={setCompletedMission}
            onSceneLoadState={({ loading, error }) => {
              setSceneLoading(loading);
              setSceneError(error);
            }}
          />
        </Canvas>
      </SceneErrorBoundary>

      <MissionHUD missions={missions} completedMission={completedMission} />
      <AmbientLoop />

      {sceneLoading && !sceneError && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/55 backdrop-blur-[1px]">
          <div className="rounded-md border border-cyan-500/50 bg-gray-950/80 px-4 py-2 text-sm text-cyan-100">
            Loading generated scene…
          </div>
        </div>
      )}

      {sceneError && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/80 px-6">
          <div className="max-w-xl rounded-lg border border-amber-500/50 bg-amber-950/40 p-5 text-amber-50 space-y-2">
            <h2 className="text-lg font-semibold">Could not load this game scene</h2>
            <p className="text-sm text-amber-100/90">{sceneError}</p>
            <p className="text-xs text-amber-200/80">Try refreshing the page. If this keeps happening over port-forward, run frontend in production mode (next build + next start).</p>
          </div>
        </div>
      )}

      {interactionPrompt && (
        <div className="absolute top-[30%] left-1/2 -translate-x-1/2 pointer-events-none select-none">
          <div className={`px-5 py-2 rounded-lg text-center backdrop-blur-sm animate-fade-in ${
            isActive
              ? 'bg-green-900/70 border border-green-500/50'
              : 'bg-black/70 border border-white/20'
          }`}>
            <div className="text-white text-sm font-medium">{interactionPrompt.action}</div>
            {!isActive && (
              <div className="flex items-center justify-center gap-2 mt-1">
                <kbd className="bg-white/20 text-white text-xs px-2 py-0.5 rounded font-mono border border-white/30">E</kbd>
              </div>
            )}
          </div>
        </div>
      )}

      <div className="absolute bottom-16 left-1/2 -translate-x-1/2 w-[90%] max-w-2xl pointer-events-none select-none">
        {commentary.length > 0 && (
          <div className="flex flex-col items-center gap-1 animate-fade-in">
            {commentary.map((line, i) => (
              <div
                key={i}
                className="bg-black/75 backdrop-blur-sm px-5 py-1.5 rounded-md text-white text-base font-medium tracking-wide text-center"
                style={{ textShadow: '0 1px 4px rgba(0,0,0,0.8)' }}
              >
                {line}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 bg-black/50 backdrop-blur-sm px-4 py-1.5 rounded-lg text-xs text-gray-400 pointer-events-none select-none">
        WASD: Move | Space: Jump | E: Interact | Mouse: Look | Click to lock cursor
      </div>
    </div>
  );
}

export default function UniverseViewer({ sessionId, engine = 'godot', unrealPlayerUrl }: UniverseViewerProps) {
  if (engine === 'godot') {
    return <GodotUniverseViewer sessionId={sessionId} />;
  }

  if (engine === 'unreal') {
    return <UnrealStreamViewer sessionId={sessionId} playerUrl={unrealPlayerUrl} />;
  }

  return <ThreeUniverseViewer sessionId={sessionId} />;
}
