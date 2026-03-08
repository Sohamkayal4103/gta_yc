'use client';

import { FormEvent, useState } from 'react';
import { useRouter } from 'next/navigation';

export default function UnrealLandingPage() {
  const router = useRouter();
  const [sessionId, setSessionId] = useState('');
  const [playerUrl, setPlayerUrl] = useState('http://127.0.0.1:80');

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!sessionId.trim()) return;
    const q = playerUrl.trim() ? `?playerUrl=${encodeURIComponent(playerUrl.trim())}` : '';
    router.push(`/unreal/${encodeURIComponent(sessionId.trim())}${q}`);
  };

  return (
    <main className="min-h-screen flex items-center justify-center p-6">
      <form onSubmit={onSubmit} className="w-full max-w-xl space-y-4 bg-gray-900/60 rounded-xl p-6 border border-gray-700">
        <h1 className="text-2xl font-semibold">Connect to Unreal Pixel Streaming</h1>
        <p className="text-sm text-gray-400">Enter a generated session ID and Pixel Streaming player URL.</p>

        <label className="block text-sm">
          <span className="text-gray-300">Session ID</span>
          <input
            className="mt-1 w-full rounded bg-black/40 border border-gray-600 px-3 py-2"
            placeholder="e.g. 313b9d9d"
            value={sessionId}
            onChange={(e) => setSessionId(e.target.value)}
          />
        </label>

        <label className="block text-sm">
          <span className="text-gray-300">Player URL</span>
          <input
            className="mt-1 w-full rounded bg-black/40 border border-gray-600 px-3 py-2"
            placeholder="http://server-ip:80"
            value={playerUrl}
            onChange={(e) => setPlayerUrl(e.target.value)}
          />
        </label>

        <button className="px-4 py-2 rounded bg-blue-600 hover:bg-blue-500">Open Stream</button>
      </form>
    </main>
  );
}
