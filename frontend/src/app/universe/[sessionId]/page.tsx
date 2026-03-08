'use client';

import dynamic from 'next/dynamic';
import { useParams, useSearchParams } from 'next/navigation';

const UniverseViewer = dynamic(() => import('@/components/UniverseViewer'), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-screen">
      <p className="text-gray-400">Loading Universe runtime...</p>
    </div>
  ),
});

export default function UniversePage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const sessionId = params.sessionId as string;
  const requestedEngine = searchParams.get('engine');
  const playerUrl = searchParams.get('playerUrl') ?? undefined;
  const engine = requestedEngine === 'three' || requestedEngine === 'unreal' ? requestedEngine : 'godot';

  return <UniverseViewer sessionId={sessionId} engine={engine} unrealPlayerUrl={playerUrl} />;
}
