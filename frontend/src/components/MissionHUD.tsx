'use client';

import { useEffect, useState } from 'react';
import { Mission } from '@/lib/api';

interface MissionHUDProps {
  missions: Mission[];
  completedMission: Mission | null;
}

export default function MissionHUD({ missions, completedMission }: MissionHUDProps) {
  const [showBanner, setShowBanner] = useState(false);
  const [bannerTitle, setBannerTitle] = useState('');

  useEffect(() => {
    if (completedMission) {
      setBannerTitle(completedMission.title);
      setShowBanner(true);
      const timer = setTimeout(() => setShowBanner(false), 3000);
      return () => clearTimeout(timer);
    }
  }, [completedMission]);

  if (missions.length === 0) return null;

  return (
    <>
      {/* Mission panel — top-left, GTA style */}
      <div className="absolute top-4 left-4 pointer-events-none select-none" style={{ minWidth: 220 }}>
        <div className="bg-black/70 backdrop-blur-sm rounded-lg px-4 py-3 border border-yellow-500/30">
          <div className="text-yellow-400 text-xs font-bold tracking-widest mb-2" style={{ fontFamily: 'monospace' }}>
            MISSIONS
          </div>
          <div className="space-y-2">
            {missions.map(mission => {
              const done = mission.objectives.filter(o => o.completed).length;
              const total = mission.objectives.length;
              return (
                <div key={mission.id} className="flex items-center gap-2">
                  {mission.completed ? (
                    <span className="text-green-400 text-sm">&#10003;</span>
                  ) : (
                    <span className="text-gray-500 text-sm">&#9675;</span>
                  )}
                  <div className="flex-1">
                    <div className={`text-xs font-medium ${mission.completed ? 'text-green-400 line-through' : 'text-white'}`}>
                      {mission.title}
                    </div>
                  </div>
                  <div className={`text-xs font-mono ${mission.completed ? 'text-green-400' : 'text-gray-400'}`}>
                    {done}/{total}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* MISSION PASSED! banner */}
      {showBanner && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none select-none z-50">
          <div
            className="text-center"
            style={{
              animation: 'missionPassedIn 0.4s ease-out forwards, missionPassedOut 0.8s ease-in 2.2s forwards',
            }}
          >
            <div
              className="text-5xl font-black tracking-wider"
              style={{
                color: '#ffd700',
                textShadow: '0 0 20px rgba(255, 215, 0, 0.6), 0 4px 12px rgba(0,0,0,0.8)',
                fontFamily: 'Impact, sans-serif',
              }}
            >
              MISSION PASSED!
            </div>
            <div className="text-white text-xl mt-2 font-bold" style={{ textShadow: '0 2px 8px rgba(0,0,0,0.8)' }}>
              {bannerTitle}
            </div>
          </div>
        </div>
      )}

      <style jsx>{`
        @keyframes missionPassedIn {
          0% { transform: scale(0.3); opacity: 0; }
          100% { transform: scale(1); opacity: 1; }
        }
        @keyframes missionPassedOut {
          0% { opacity: 1; }
          100% { opacity: 0; }
        }
      `}</style>
    </>
  );
}
