'use client';

import { useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { ScenePerson, PersonDetails } from '@/lib/api';

interface HumanFigureProps {
  person: ScenePerson;
  isBeingGreeted?: boolean;
  details?: PersonDetails;
  playerPosition?: [number, number, number];
}

export default function HumanFigure({ person, isBeingGreeted, details, playerPosition }: HumanFigureProps) {
  const s = person.height / 1.75;
  const facingRad = (person.facing * Math.PI) / 180;
  const isSitting = person.pose === 'sitting';

  const groupRef = useRef<THREE.Group>(null!);
  const greetProgressRef = useRef(0);

  const hairColor = details?.hair_color || '#3a2a1a';
  const hairStyle = details?.hair_style || 'short';
  const eyeColor = details?.eye_color || '#4a3520';
  const shoeColor = details?.shoe_color || '#222222';
  const hasFacialHair = details?.facial_hair && details.facial_hair !== 'none';

  // Smooth greeting animation
  useFrame((_, delta) => {
    if (!groupRef.current) return;
    const dt = Math.min(delta, 0.05);

    if (isBeingGreeted) {
      greetProgressRef.current = Math.min(1, greetProgressRef.current + 3 * dt);

      // Rotate to face player
      if (playerPosition) {
        const dx = playerPosition[0] - person.position[0];
        const dz = playerPosition[2] - person.position[2];
        const targetRot = Math.atan2(dx, dz);
        let diff = targetRot - groupRef.current.rotation.y;
        while (diff > Math.PI) diff -= 2 * Math.PI;
        while (diff < -Math.PI) diff += 2 * Math.PI;
        groupRef.current.rotation.y += diff * Math.min(1, 5 * dt);
      }
    } else {
      greetProgressRef.current = Math.max(0, greetProgressRef.current - 3 * dt);
      // Return to original facing
      let diff = facingRad - groupRef.current.rotation.y;
      while (diff > Math.PI) diff -= 2 * Math.PI;
      while (diff < -Math.PI) diff += 2 * Math.PI;
      groupRef.current.rotation.y += diff * Math.min(1, 3 * dt);
    }
  });

  // Key body proportions
  const headR = 0.09 * s;
  const neckH = 0.06 * s;
  const torsoH = 0.48 * s;
  const torsoW = 0.36 * s;
  const torsoD = 0.20 * s;
  const hipW = 0.32 * s;
  const hipH = 0.12 * s;
  const upperArmL = 0.28 * s;
  const lowerArmL = 0.24 * s;
  const upperArmR_r = 0.04 * s;
  const lowerArmR_r = 0.032 * s;
  const handR = 0.035 * s;
  const upperLegL = 0.40 * s;
  const lowerLegL = 0.38 * s;
  const upperLegR_r = 0.058 * s;
  const lowerLegR_r = 0.048 * s;
  const footW = 0.09 * s;
  const footH = 0.05 * s;
  const footD = 0.20 * s;
  const shoulderSpread = 0.22 * s;
  const hipSpread = 0.10 * s;

  // Y positions (standing)
  const footY = footH / 2;
  const lowerLegY = footH + lowerLegL / 2;
  const kneeY = footH + lowerLegL;
  const upperLegY = kneeY + upperLegL / 2;
  const hipY = kneeY + upperLegL;
  const torsoBaseY = hipY + hipH;
  const torsoY = torsoBaseY + torsoH / 2;
  const shoulderY = torsoBaseY + torsoH;
  const neckY = shoulderY + neckH / 2;
  const headY = shoulderY + neckH + headR;

  const upperArmY = shoulderY - upperArmL / 2;
  const elbowY = shoulderY - upperArmL;
  const lowerArmY = elbowY - lowerArmL / 2;
  const handY = elbowY - lowerArmL;

  const sitDrop = isSitting ? (upperLegL + lowerLegL - 0.4 * s) : 0;

  // Greeting arm interpolation helper
  const gp = greetProgressRef.current;

  return (
    <group ref={groupRef} position={person.position} rotation={[0, facingRad, 0]}>
      <group position={[0, -sitDrop, 0]}>
        {/* Head */}
        <mesh position={[0, headY, 0]} castShadow>
          <sphereGeometry args={[headR, 20, 20]} />
          <meshStandardMaterial color={person.skin_color} roughness={0.7} />
        </mesh>

        {/* === FACIAL FEATURES === */}
        {/* Eyes - white spheres with iris */}
        {[-1, 1].map(side => (
          <group key={`eye${side}`}>
            {/* Eye white */}
            <mesh position={[side * 0.03 * s, headY + 0.01 * s, -headR * 0.85]}>
              <sphereGeometry args={[0.015 * s, 8, 8]} />
              <meshStandardMaterial color="#f8f8f0" roughness={0.3} />
            </mesh>
            {/* Iris */}
            <mesh position={[side * 0.03 * s, headY + 0.01 * s, -headR * 0.95]}>
              <sphereGeometry args={[0.008 * s, 8, 8]} />
              <meshStandardMaterial color={eyeColor} roughness={0.4} />
            </mesh>
            {/* Pupil */}
            <mesh position={[side * 0.03 * s, headY + 0.01 * s, -headR * 0.99]}>
              <sphereGeometry args={[0.004 * s, 6, 6]} />
              <meshStandardMaterial color="#111111" roughness={0.2} />
            </mesh>
            {/* Eyebrow */}
            <mesh position={[side * 0.03 * s, headY + 0.04 * s, -headR * 0.82]}>
              <boxGeometry args={[0.035 * s, 0.006 * s, 0.01 * s]} />
              <meshStandardMaterial color={hairColor} roughness={0.8} />
            </mesh>
          </group>
        ))}

        {/* Nose */}
        <mesh position={[0, headY - 0.01 * s, -headR * 0.92]}>
          <sphereGeometry args={[0.012 * s, 8, 8]} />
          <meshStandardMaterial color={person.skin_color} roughness={0.7} />
        </mesh>

        {/* Mouth */}
        <mesh position={[0, headY - 0.035 * s, -headR * 0.88]} scale={[1.5, 0.4, 0.8]}>
          <sphereGeometry args={[0.012 * s, 8, 8]} />
          <meshStandardMaterial color="#a85050" roughness={0.6} />
        </mesh>

        {/* Ears */}
        {[-1, 1].map(side => (
          <mesh key={`ear${side}`} position={[side * headR * 0.92, headY, 0]}>
            <sphereGeometry args={[0.018 * s, 6, 6]} />
            <meshStandardMaterial color={person.skin_color} roughness={0.7} />
          </mesh>
        ))}

        {/* === HAIR === */}
        {hairStyle === 'short' && (
          <mesh position={[0, headY + headR * 0.55, -headR * 0.1]}>
            <sphereGeometry args={[headR * 0.95, 16, 16, 0, Math.PI * 2, 0, Math.PI * 0.55]} />
            <meshStandardMaterial color={hairColor} roughness={0.9} />
          </mesh>
        )}
        {hairStyle === 'long' && (
          <>
            {/* Top cap */}
            <mesh position={[0, headY + headR * 0.55, -headR * 0.1]}>
              <sphereGeometry args={[headR * 1.0, 16, 16, 0, Math.PI * 2, 0, Math.PI * 0.55]} />
              <meshStandardMaterial color={hairColor} roughness={0.9} />
            </mesh>
            {/* Back hair flowing down */}
            <mesh position={[0, headY - headR * 0.6, headR * 0.3]}>
              <boxGeometry args={[headR * 1.6, headR * 1.8, headR * 0.6]} />
              <meshStandardMaterial color={hairColor} roughness={0.9} />
            </mesh>
          </>
        )}
        {/* bald = no hair mesh */}

        {/* Facial hair */}
        {hasFacialHair && details?.facial_hair === 'beard' && (
          <mesh position={[0, headY - 0.05 * s, -headR * 0.7]} scale={[1.2, 1, 0.8]}>
            <sphereGeometry args={[0.03 * s, 8, 8]} />
            <meshStandardMaterial color={hairColor} roughness={0.9} />
          </mesh>
        )}
        {hasFacialHair && details?.facial_hair === 'mustache' && (
          <mesh position={[0, headY - 0.025 * s, -headR * 0.9]} scale={[2, 0.5, 0.5]}>
            <sphereGeometry args={[0.01 * s, 8, 8]} />
            <meshStandardMaterial color={hairColor} roughness={0.9} />
          </mesh>
        )}
        {hasFacialHair && details?.facial_hair === 'goatee' && (
          <mesh position={[0, headY - 0.055 * s, -headR * 0.8]} scale={[0.8, 1.2, 0.6]}>
            <sphereGeometry args={[0.02 * s, 8, 8]} />
            <meshStandardMaterial color={hairColor} roughness={0.9} />
          </mesh>
        )}

        {/* Neck */}
        <mesh position={[0, neckY, 0]} castShadow>
          <cylinderGeometry args={[0.035 * s, 0.04 * s, neckH, 8]} />
          <meshStandardMaterial color={person.skin_color} roughness={0.7} />
        </mesh>

        {/* Upper Torso (wider - V-shape) */}
        <mesh position={[0, torsoBaseY + torsoH * 0.75, 0]} castShadow>
          <boxGeometry args={[torsoW * 1.08, torsoH * 0.55, torsoD * 1.05]} />
          <meshStandardMaterial color={person.shirt_color} roughness={0.6} />
        </mesh>
        {/* Lower Torso (narrower - V-shape) */}
        <mesh position={[0, torsoBaseY + torsoH * 0.25, 0]} castShadow>
          <boxGeometry args={[torsoW * 0.88, torsoH * 0.52, torsoD * 0.92]} />
          <meshStandardMaterial color={person.shirt_color} roughness={0.6} />
        </mesh>

        {/* Collar / Yoke bridge */}
        <mesh position={[0, shoulderY - 0.02 * s, -torsoD * 0.35]} castShadow>
          <boxGeometry args={[torsoW * 0.9, 0.04 * s, 0.06 * s]} />
          <meshStandardMaterial color={person.shirt_color} roughness={0.5} />
        </mesh>

        {/* Hips */}
        <mesh position={[0, hipY + hipH / 2, 0]} castShadow>
          <boxGeometry args={[hipW, hipH, torsoD * 0.95]} />
          <meshStandardMaterial color={person.pants_color} roughness={0.7} />
        </mesh>

        {/* Shoulders */}
        <mesh position={[-shoulderSpread, shoulderY, 0]} castShadow>
          <sphereGeometry args={[0.05 * s, 8, 8]} />
          <meshStandardMaterial color={person.shirt_color} roughness={0.6} />
        </mesh>
        <mesh position={[shoulderSpread, shoulderY, 0]} castShadow>
          <sphereGeometry args={[0.05 * s, 8, 8]} />
          <meshStandardMaterial color={person.shirt_color} roughness={0.6} />
        </mesh>

        {/* Left arm (slight outward angle ~7°) */}
        <group position={[-shoulderSpread, shoulderY, 0]} rotation={[0, 0, -0.12]}>
          <mesh position={[0, -upperArmL / 2, 0]} castShadow>
            <capsuleGeometry args={[upperArmR_r, upperArmL, 4, 8]} />
            <meshStandardMaterial color={person.shirt_color} roughness={0.6} />
          </mesh>
          <mesh position={[0, -upperArmL, 0]} castShadow>
            <sphereGeometry args={[upperArmR_r * 1.1, 6, 6]} />
            <meshStandardMaterial color={person.skin_color} roughness={0.7} />
          </mesh>
          <mesh position={[0, -upperArmL - lowerArmL / 2, 0]} castShadow>
            <capsuleGeometry args={[lowerArmR_r, lowerArmL, 4, 8]} />
            <meshStandardMaterial color={person.skin_color} roughness={0.7} />
          </mesh>
          <mesh position={[0, -upperArmL - lowerArmL, 0]} scale={[1, 0.7, 0.5]} castShadow>
            <sphereGeometry args={[handR, 6, 6]} />
            <meshStandardMaterial color={person.skin_color} roughness={0.7} />
          </mesh>
        </group>

        {/* Right arm — slight outward angle, extends forward when greeting */}
        <group
          position={[shoulderSpread, shoulderY, 0]}
          rotation={[
            THREE.MathUtils.lerp(0, Math.PI * 0.45, gp),
            0,
            THREE.MathUtils.lerp(0.12, 0, gp),
          ]}
        >
          <mesh position={[0, -upperArmL / 2, 0]} castShadow>
            <capsuleGeometry args={[upperArmR_r, upperArmL, 4, 8]} />
            <meshStandardMaterial color={person.shirt_color} roughness={0.6} />
          </mesh>
          <mesh position={[0, -upperArmL, 0]} castShadow>
            <sphereGeometry args={[upperArmR_r * 1.1, 6, 6]} />
            <meshStandardMaterial color={person.skin_color} roughness={0.7} />
          </mesh>
          <group position={[0, -upperArmL, 0]} rotation={[THREE.MathUtils.lerp(0, Math.PI * 0.25, gp), 0, 0]}>
            <mesh position={[0, -lowerArmL / 2, 0]} castShadow>
              <capsuleGeometry args={[lowerArmR_r, lowerArmL, 4, 8]} />
              <meshStandardMaterial color={person.skin_color} roughness={0.7} />
            </mesh>
            <mesh position={[0, -lowerArmL, 0]} scale={[1, 0.7, 0.5]} castShadow>
              <sphereGeometry args={[handR, 6, 6]} />
              <meshStandardMaterial color={person.skin_color} roughness={0.7} />
            </mesh>
          </group>
        </group>

        {/* Legs */}
        {[-1, 1].map(side => {
          const spread = side === -1 ? -hipSpread : hipSpread;
          return (
            <group key={`leg${side}`}>
              <mesh
                position={[spread, isSitting ? hipY - 0.05 * s : upperLegY, isSitting ? upperLegL / 2 : 0]}
                rotation={[isSitting ? Math.PI / 2 : 0, 0, 0]}
                castShadow
              >
                <capsuleGeometry args={[upperLegR_r, upperLegL, 4, 8]} />
                <meshStandardMaterial color={person.pants_color} roughness={0.7} />
              </mesh>
              <mesh
                position={[spread, isSitting ? hipY - 0.05 * s : kneeY, isSitting ? upperLegL : 0]}
                castShadow
              >
                <sphereGeometry args={[upperLegR_r * 1.05, 6, 6]} />
                <meshStandardMaterial color={person.pants_color} roughness={0.7} />
              </mesh>
              <mesh
                position={[spread, isSitting ? hipY - 0.05 * s - lowerLegL / 2 : lowerLegY, isSitting ? upperLegL : 0]}
                castShadow
              >
                <capsuleGeometry args={[lowerLegR_r, lowerLegL, 4, 8]} />
                <meshStandardMaterial color={person.pants_color} roughness={0.7} />
              </mesh>
              <mesh
                position={[spread, isSitting ? hipY - 0.05 * s - lowerLegL : footY, isSitting ? upperLegL + footD / 3 : footD / 6]}
                castShadow
              >
                <boxGeometry args={[footW, footH, footD]} />
                <meshStandardMaterial color={shoeColor} roughness={0.8} />
              </mesh>
            </group>
          );
        })}
      </group>
    </group>
  );
}
