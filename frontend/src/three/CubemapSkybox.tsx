'use client';

import { useThree } from '@react-three/fiber';
import { useEffect } from 'react';
import * as THREE from 'three';

interface CubemapSkyboxProps {
  sessionId: string;
}

export default function CubemapSkybox({ sessionId }: CubemapSkyboxProps) {
  const { scene } = useThree();

  useEffect(() => {
    // Three.js CubeTexture order: +X (right), -X (left), +Y (up), -Y (down), +Z (front), -Z (back)
    // Our API: front, back, left, right, up, down
    const directions = ['right', 'left', 'up', 'down', 'front', 'back'];
    const urls = directions.map(
      (dir) => `/api/universe/${sessionId}/cubemap/${dir}`
    );

    const loader = new THREE.CubeTextureLoader();
    loader.load(urls, (texture) => {
      scene.background = texture;
      scene.environment = texture;
    });

    return () => {
      if (scene.background instanceof THREE.CubeTexture) {
        scene.background.dispose();
        scene.background = null;
      }
      if (scene.environment instanceof THREE.CubeTexture) {
        scene.environment.dispose();
        scene.environment = null;
      }
    };
  }, [sessionId, scene]);

  return null;
}
