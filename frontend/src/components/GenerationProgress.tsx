'use client';

import { useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getStatus, getLogs, SessionStatus } from '@/lib/api';

interface GenerationProgressProps {
  sessionId: string;
}

export default function GenerationProgress({ sessionId }: GenerationProgressProps) {
  const router = useRouter();
  const terminalRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<SessionStatus>({
    status: 'processing',
    stage: 'initializing',
    progress: 0,
    message: 'Starting...',
  });
  const [logs, setLogs] = useState<string[]>([]);

  useEffect(() => {
    const interval = setInterval(async () => {
      try {
        const [s, l] = await Promise.all([getStatus(sessionId), getLogs(sessionId)]);
        setStatus(s);
        setLogs(l);
        if (s.status === 'complete' || s.status === 'error') {
          clearInterval(interval);
        }
      } catch {
        // ignore polling errors
      }
    }, 1500);
    return () => clearInterval(interval);
  }, [sessionId]);

  // Auto-scroll terminal
  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="max-w-2xl w-full mx-auto space-y-6">
      <h2 className="text-xl font-semibold text-center">Building Your Universe</h2>

      {/* Progress bar */}
      <div className="w-full bg-gray-800 rounded-full h-3">
        <div
          className="bg-blue-500 h-3 rounded-full transition-all duration-500"
          style={{ width: `${status.progress}%` }}
        />
      </div>
      <p className="text-gray-500 text-xs text-center">{status.stage} — {status.progress}%</p>

      {/* Terminal console */}
      <div className="space-y-1">
        <div className="flex items-center gap-2 text-xs text-gray-500 uppercase tracking-wider font-bold border-b border-gray-800 pb-1">
          <span className={`w-2 h-2 rounded-full ${status.status === 'processing' ? 'bg-green-500 animate-pulse' : status.status === 'complete' ? 'bg-green-500' : 'bg-red-500'}`} />
          System Console
        </div>
        <div
          ref={terminalRef}
          className="bg-[#050508] border border-gray-800 rounded-lg p-4 h-64 overflow-y-auto font-mono text-xs leading-relaxed"
          style={{ color: '#00ffcc' }}
        >
          {logs.length === 0 ? (
            <span className="text-gray-600">Waiting for server logs...</span>
          ) : (
            logs.map((line, i) => (
              <div key={i} className={line.includes('ERROR') || line.includes('CRITICAL') ? 'text-red-400' : ''}>
                {`> ${line}`}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Action buttons */}
      {status.status === 'complete' && (
        <div className="text-center">
          <button
            onClick={() => router.push(`/universe/${sessionId}`)}
            className="px-8 py-3 bg-green-600 hover:bg-green-500 rounded-lg font-semibold transition-colors text-lg"
          >
            Enter Universe
          </button>
        </div>
      )}

      {status.status === 'error' && (
        <div className="text-red-400 bg-red-900/30 rounded-lg p-4 text-center">
          <p className="font-medium">Generation failed</p>
          <p className="text-sm mt-1">{status.message}</p>
        </div>
      )}
    </div>
  );
}
