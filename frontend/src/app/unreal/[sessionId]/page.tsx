'use client';

import { useParams, useSearchParams } from 'next/navigation';
import UnrealStreamViewer from '@/components/UnrealStreamViewer';

export default function UnrealSessionPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const sessionId = params.sessionId as string;
  const playerUrl = searchParams.get('playerUrl') ?? undefined;

  return <UnrealStreamViewer sessionId={sessionId} playerUrl={playerUrl} />;
}
