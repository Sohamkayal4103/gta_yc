'use client';

import { useCallback, useRef, useState } from 'react';

const DIRECTIONS = ['front', 'back', 'left', 'right', 'up', 'down'] as const;
type Direction = (typeof DIRECTIONS)[number];

const DIRECTION_LABELS: Record<Direction, string> = {
  front: 'Front',
  back: 'Back',
  left: 'Left',
  right: 'Right',
  up: 'Up (Ceiling)',
  down: 'Down (Floor)',
};

interface UploadGridProps {
  images: Record<string, File>;
  onImagesChange: (images: Record<string, File>) => void;
}

export default function UploadGrid({ images, onImagesChange }: UploadGridProps) {
  const [previews, setPreviews] = useState<Record<string, string>>({});
  const fileInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  const handleFileSelect = useCallback(
    (direction: Direction, file: File) => {
      const updated = { ...images, [direction]: file };
      onImagesChange(updated);

      const url = URL.createObjectURL(file);
      setPreviews((prev) => {
        if (prev[direction]) URL.revokeObjectURL(prev[direction]);
        return { ...prev, [direction]: url };
      });
    },
    [images, onImagesChange]
  );

  const uploadCount = Object.keys(images).length;

  return (
    <div>
      <p className="text-sm text-gray-400 mb-4">
        {uploadCount}/6 photos uploaded — Take one photo from each direction
      </p>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
        {DIRECTIONS.map((dir) => (
          <div
            key={dir}
            onClick={() => fileInputRefs.current[dir]?.click()}
            className={`relative aspect-square rounded-xl border-2 border-dashed cursor-pointer
              flex flex-col items-center justify-center gap-2 transition-all
              ${
                images[dir]
                  ? 'border-green-500 bg-green-500/10'
                  : 'border-gray-600 hover:border-gray-400 bg-gray-900'
              }`}
          >
            {previews[dir] ? (
              <img
                src={previews[dir]}
                alt={dir}
                className="absolute inset-0 w-full h-full object-cover rounded-xl opacity-80"
              />
            ) : (
              <>
                <svg className="w-8 h-8 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 9a2 2 0 012-2h.93a2 2 0 001.664-.89l.812-1.22A2 2 0 0110.07 4h3.86a2 2 0 011.664.89l.812 1.22A2 2 0 0018.07 7H19a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V9z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 13a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </>
            )}
            <span className={`text-sm font-medium z-10 ${previews[dir] ? 'bg-black/60 px-2 py-0.5 rounded' : ''}`}>
              {DIRECTION_LABELS[dir]}
            </span>
            <input
              ref={(el) => { fileInputRefs.current[dir] = el; }}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFileSelect(dir, file);
              }}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
