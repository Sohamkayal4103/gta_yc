'use client';

import { useState } from 'react';
import Link from 'next/link';
import UploadGrid from '@/components/UploadGrid';
import GenerationProgress from '@/components/GenerationProgress';
import { generate3D } from '@/lib/api';

export default function Upload3DPage() {
  const [images, setImages] = useState<Record<string, File>>({});
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleGenerate = async () => {
    if (Object.keys(images).length === 0) return;
    setLoading(true);
    setError(null);
    try {
      const res = await generate3D(images);
      setSessionId(res.session_id);
    } catch (e: any) {
      setError(e.message || 'Failed to start generation');
    } finally {
      setLoading(false);
    }
  };

  if (sessionId) {
    return (
      <main className="min-h-screen flex items-center justify-center p-8">
        <GenerationProgress sessionId={sessionId} />
      </main>
    );
  }

  return (
    <main className="min-h-screen flex flex-col items-center justify-center p-8">
      <div className="max-w-2xl w-full space-y-8">
        <div className="text-center space-y-2">
          <h1 className="text-4xl font-bold bg-gradient-to-r from-blue-400 to-purple-500 bg-clip-text text-transparent">
            RealmCast
          </h1>
          <p className="text-gray-400">
            Upload 6 directional photos of your room to build a 3D universe
          </p>
          <p className="text-xs text-gray-500">
            Need video-driven segmentation flow?{' '}
            <Link href="/video" className="text-cyan-400 hover:text-cyan-300 underline">
              Open Video Pipeline
            </Link>
          </p>
        </div>

        <UploadGrid images={images} onImagesChange={setImages} />

        {error && (
          <p className="text-red-400 text-center text-sm">{error}</p>
        )}

        <div className="flex justify-center">
          <button
            onClick={handleGenerate}
            disabled={Object.keys(images).length === 0 || loading}
            className="px-8 py-3 bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 disabled:cursor-not-allowed
              rounded-lg font-semibold transition-colors"
          >
            {loading ? 'Starting...' : `Build Universe (${Object.keys(images).length} photos)`}
          </button>
        </div>
      </div>
    </main>
  );
}
