'use client';

import { SceneObject, InteractionType, DoorReveal, ContainerContents, ObjectDetails } from '@/lib/api';
import { ActiveInteraction } from './ThirdPersonController';
import * as THREE from 'three';
import { Html } from '@react-three/drei';

interface PBRObjectProps {
  obj: SceneObject;
  activeInteraction?: ActiveInteraction | null;
  doorReveal?: DoorReveal;
  containerContents?: ContainerContents;
  objectDetails?: ObjectDetails;
}

function guessInteraction(name: string | null | undefined): InteractionType {
  const n = String(name ?? '').toLowerCase();
  if (/chair|couch|sofa|bench|stool|seat/.test(n)) return 'sit';
  if (/whiteboard|blackboard|chalkboard|board/.test(n)) return 'write';
  if (/laptop|monitor|computer|tv|television|microwave|printer|phone|coffee|machine|screen/.test(n)) return 'use';
  if (/door|cabinet|drawer|fridge|closet|cupboard|suitcase/.test(n)) return 'open';
  if (/lamp|light|switch|fan/.test(n)) return 'toggle';
  return 'none';
}

function guessObjectType(name: string | null | undefined): string {
  const n = String(name ?? '').toLowerCase();
  if (/suitcase|luggage|briefcase/.test(n)) return 'suitcase';
  if (/desk|table/.test(n)) return 'table';
  if (/chair|office.?chair/.test(n)) return 'chair';
  if (/couch|sofa/.test(n)) return 'couch';
  if (/monitor|screen|tv|television/.test(n)) return 'monitor';
  if (/lamp/.test(n)) return 'lamp';
  if (/door/.test(n)) return 'door';
  if (/shelf|bookshelf|shelving/.test(n)) return 'shelf';
  if (/cabinet|cupboard|dresser/.test(n)) return 'cabinet';
  if (/bed/.test(n)) return 'bed';
  if (/plant|pot|fern|succulent/.test(n)) return 'plant';
  if (/window/.test(n)) return 'window';
  if (/picture|painting|frame|poster|art/.test(n)) return 'picture';
  if (/rug|carpet|mat/.test(n)) return 'rug';
  return 'generic';
}

function getGeometry(shape: string, size: [number, number, number]) {
  switch (shape) {
    case 'sphere':
      return <sphereGeometry args={[size[0] / 2, 32, 32]} />;
    case 'cylinder':
      return <cylinderGeometry args={[size[0] / 2, size[0] / 2, size[1], 32]} />;
    case 'plane':
      return <planeGeometry args={[size[0], size[1]]} />;
    case 'box':
    default:
      return <boxGeometry args={size} />;
  }
}

// --- Composite shapes ---

function TableShape({ size, color, roughness, metalness }: { size: [number, number, number]; color: string; roughness: number; metalness: number }) {
  const [w, h, d] = size;
  const topThick = Math.min(h * 0.08, 0.05);
  const legR = Math.min(w, d) * 0.04;
  const legH = h - topThick;
  const insetX = w * 0.42;
  const insetZ = d * 0.42;
  return (
    <group>
      <mesh position={[0, h / 2 - topThick / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[w, topThick, d]} />
        <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
      </mesh>
      {[[-insetX, -insetZ], [insetX, -insetZ], [-insetX, insetZ], [insetX, insetZ]].map(([lx, lz], i) => (
        <mesh key={i} position={[lx, -topThick / 2, lz]} castShadow>
          <cylinderGeometry args={[legR, legR, legH, 8]} />
          <meshStandardMaterial color={color} roughness={roughness + 0.1} metalness={metalness} />
        </mesh>
      ))}
    </group>
  );
}

function ChairShape({ size, color, roughness, metalness }: { size: [number, number, number]; color: string; roughness: number; metalness: number }) {
  const [w, h, d] = size;
  const seatH = h * 0.45;
  const seatThick = Math.min(h * 0.06, 0.04);
  const backH = h * 0.45;
  const backThick = Math.min(d * 0.1, 0.04);
  const legR = Math.min(w, d) * 0.04;
  const legH = seatH - seatThick / 2;
  const insetX = w * 0.38;
  const insetZ = d * 0.38;
  return (
    <group>
      <mesh position={[0, seatH - h / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[w * 0.9, seatThick, d * 0.85]} />
        <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
      </mesh>
      <mesh position={[0, seatH + backH / 2 - h / 2, -d * 0.4]} castShadow>
        <boxGeometry args={[w * 0.85, backH, backThick]} />
        <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
      </mesh>
      {[[-insetX, -insetZ], [insetX, -insetZ], [-insetX, insetZ], [insetX, insetZ]].map(([lx, lz], i) => (
        <mesh key={i} position={[lx, -h / 2 + legH / 2, lz]} castShadow>
          <cylinderGeometry args={[legR, legR, legH, 8]} />
          <meshStandardMaterial color={color} roughness={roughness + 0.15} metalness={Math.min(metalness + 0.3, 1)} />
        </mesh>
      ))}
    </group>
  );
}

function MonitorShape({ size, color, roughness, metalness }: { size: [number, number, number]; color: string; roughness: number; metalness: number }) {
  const [w, h, d] = size;
  const screenThick = Math.min(d * 0.3, 0.04);
  const standW = w * 0.15;
  const standH = h * 0.25;
  const baseW = w * 0.4;
  const baseD = d * 1.2;
  const baseH = Math.min(h * 0.04, 0.02);
  return (
    <group>
      <mesh position={[0, h * 0.15, 0]} castShadow receiveShadow>
        <boxGeometry args={[w, h * 0.7, screenThick]} />
        <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
      </mesh>
      <mesh position={[0, h * 0.15, screenThick / 2 + 0.001]}>
        <planeGeometry args={[w * 0.92, h * 0.65]} />
        <meshStandardMaterial color="#1a1a2e" roughness={0.2} metalness={0.1} />
      </mesh>
      <mesh position={[0, -h * 0.15, -screenThick]} castShadow>
        <boxGeometry args={[standW, standH, screenThick * 1.5]} />
        <meshStandardMaterial color="#555" roughness={0.4} metalness={0.6} />
      </mesh>
      <mesh position={[0, -h / 2 + baseH / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[baseW, baseH, baseD]} />
        <meshStandardMaterial color="#555" roughness={0.4} metalness={0.6} />
      </mesh>
    </group>
  );
}

function LampShape({ size, color, roughness, metalness }: { size: [number, number, number]; color: string; roughness: number; metalness: number }) {
  const [w, h] = size;
  const baseR = w * 0.35;
  const baseH = h * 0.05;
  const poleR = w * 0.04;
  const poleH = h * 0.65;
  const shadeTopR = w * 0.15;
  const shadeBotR = w * 0.4;
  const shadeH = h * 0.25;
  return (
    <group>
      <mesh position={[0, -h / 2 + baseH / 2, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[baseR, baseR * 1.1, baseH, 16]} />
        <meshStandardMaterial color="#444" roughness={0.5} metalness={0.5} />
      </mesh>
      <mesh position={[0, -h / 2 + baseH + poleH / 2, 0]} castShadow>
        <cylinderGeometry args={[poleR, poleR, poleH, 8]} />
        <meshStandardMaterial color="#888" roughness={0.3} metalness={0.7} />
      </mesh>
      <mesh position={[0, h / 2 - shadeH / 2, 0]} castShadow>
        <cylinderGeometry args={[shadeTopR, shadeBotR, shadeH, 16, 1, true]} />
        <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function CouchShape({ size, color, roughness, metalness }: { size: [number, number, number]; color: string; roughness: number; metalness: number }) {
  const [w, h, d] = size;
  const seatH = h * 0.4;
  const backH = h * 0.55;
  const armW = w * 0.08;
  return (
    <group>
      <mesh position={[0, seatH / 2 - h / 2, d * 0.05]} castShadow receiveShadow>
        <boxGeometry args={[w * 0.84, seatH, d * 0.85]} />
        <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
      </mesh>
      <mesh position={[0, seatH + backH / 2 - h / 2, -d * 0.38]} castShadow>
        <boxGeometry args={[w * 0.92, backH, d * 0.2]} />
        <meshStandardMaterial color={color} roughness={roughness + 0.05} metalness={metalness} />
      </mesh>
      {[-1, 1].map(side => (
        <mesh key={side} position={[side * (w / 2 - armW / 2), seatH / 2 + seatH * 0.2 - h / 2, 0]} castShadow>
          <boxGeometry args={[armW, seatH * 0.7, d * 0.9]} />
          <meshStandardMaterial color={color} roughness={roughness + 0.05} metalness={metalness} />
        </mesh>
      ))}
    </group>
  );
}

function ShelfShape({ size, color, roughness, metalness }: { size: [number, number, number]; color: string; roughness: number; metalness: number }) {
  const [w, h, d] = size;
  const thick = Math.min(h * 0.03, 0.025);
  const sideThick = Math.min(w * 0.04, 0.025);
  const numShelves = Math.max(2, Math.round(h / 0.35));
  const spacing = h / numShelves;
  return (
    <group>
      {[-1, 1].map(side => (
        <mesh key={side} position={[side * (w / 2 - sideThick / 2), 0, 0]} castShadow receiveShadow>
          <boxGeometry args={[sideThick, h, d]} />
          <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
        </mesh>
      ))}
      {Array.from({ length: numShelves + 1 }).map((_, i) => (
        <mesh key={i} position={[0, -h / 2 + i * spacing, 0]} castShadow receiveShadow>
          <boxGeometry args={[w - sideThick * 2, thick, d]} />
          <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
        </mesh>
      ))}
      <mesh position={[0, 0, -d / 2 + 0.005]} receiveShadow>
        <boxGeometry args={[w - sideThick * 2, h, 0.01]} />
        <meshStandardMaterial color={color} roughness={roughness + 0.1} metalness={metalness} />
      </mesh>
    </group>
  );
}

function DoorShape({ size, color, roughness, metalness, isOpen, doorReveal }: {
  size: [number, number, number]; color: string; roughness: number; metalness: number;
  isOpen?: boolean; doorReveal?: DoorReveal;
}) {
  const [w, h, d] = size;
  const frameW = w * 0.06;
  return (
    <group>
      {/* Door panel — rotates when open */}
      <group rotation={[0, isOpen ? Math.PI * 0.4 : 0, 0]} position={[isOpen ? -w * 0.3 : 0, 0, 0]}>
        <mesh position={[0, 0, 0]} castShadow receiveShadow>
          <boxGeometry args={[w - frameW * 2, h - frameW, d]} />
          <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
        </mesh>
        {/* Handle */}
        <mesh position={[w * 0.35, -h * 0.05, d / 2 + 0.01]} castShadow>
          <sphereGeometry args={[0.025, 8, 8]} />
          <meshStandardMaterial color="#c0a050" roughness={0.3} metalness={0.8} />
        </mesh>
      </group>
      {/* Frame top */}
      <mesh position={[0, h / 2 - frameW / 2, 0]} castShadow>
        <boxGeometry args={[w, frameW, d * 1.3]} />
        <meshStandardMaterial color="#f5f0e8" roughness={0.6} metalness={0.05} />
      </mesh>
      {/* Frame left */}
      <mesh position={[-w / 2 + frameW / 2, 0, 0]} castShadow>
        <boxGeometry args={[frameW, h, d * 1.3]} />
        <meshStandardMaterial color="#f5f0e8" roughness={0.6} metalness={0.05} />
      </mesh>
      {/* Frame right */}
      <mesh position={[w / 2 - frameW / 2, 0, 0]} castShadow>
        <boxGeometry args={[frameW, h, d * 1.3]} />
        <meshStandardMaterial color="#f5f0e8" roughness={0.6} metalness={0.05} />
      </mesh>

      {/* Door reveal — room behind when open */}
      {isOpen && doorReveal && (
        <group position={[0, 0, d + 0.8]}>
          {/* Floor */}
          <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -h / 2 + 0.01, 0]} receiveShadow>
            <planeGeometry args={[w * 1.5, 1.6]} />
            <meshStandardMaterial color={doorReveal.floor_color} roughness={0.8} />
          </mesh>
          {/* Back wall */}
          <mesh position={[0, 0, 0.8]}>
            <planeGeometry args={[w * 1.5, h]} />
            <meshStandardMaterial color={doorReveal.wall_color} roughness={0.7} />
          </mesh>
          {/* Dim light */}
          <pointLight color="#fff5e0" intensity={0.5} distance={3} position={[0, h * 0.3, 0.4]} />
          {/* Visible objects */}
          {doorReveal.visible_objects?.map((item, i) => (
            <mesh key={i} position={item.offset} castShadow>
              {item.shape === 'sphere'
                ? <sphereGeometry args={[item.size[0] / 2, 12, 12]} />
                : item.shape === 'cylinder'
                  ? <cylinderGeometry args={[item.size[0] / 2, item.size[0] / 2, item.size[1], 12]} />
                  : <boxGeometry args={item.size} />
              }
              <meshStandardMaterial color={item.color} roughness={0.6} />
            </mesh>
          ))}
        </group>
      )}
    </group>
  );
}

function SuitcaseShape({ size, color, roughness, metalness, isOpen, containerContents }: {
  size: [number, number, number]; color: string; roughness: number; metalness: number;
  isOpen?: boolean; containerContents?: ContainerContents;
}) {
  const [w, h, d] = size;
  const handleW = w * 0.3;
  const handleH = h * 0.15;
  const wheelR = Math.min(w, d) * 0.06;
  const latchSize = 0.02;
  return (
    <group>
      {/* Body */}
      <mesh position={[0, isOpen ? -h * 0.1 : 0, 0]} castShadow receiveShadow>
        <boxGeometry args={[w, h * (isOpen ? 0.5 : 1), d]} />
        <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
      </mesh>
      {/* Lid (opens upward) */}
      {isOpen && (
        <group position={[0, h * 0.15, -d * 0.35]} rotation={[-Math.PI * 0.35, 0, 0]}>
          <mesh castShadow>
            <boxGeometry args={[w * 0.98, h * 0.45, d * 0.95]} />
            <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
          </mesh>
        </group>
      )}
      {/* Handle on top */}
      <mesh position={[0, h / 2 + handleH / 2, 0]} castShadow>
        <boxGeometry args={[handleW, handleH, 0.02]} />
        <meshStandardMaterial color="#333" roughness={0.4} metalness={0.6} />
      </mesh>
      {/* Wheels */}
      {[[-1, -1], [1, -1], [-1, 1], [1, 1]].map(([sx, sz], i) => (
        <mesh key={i} position={[sx * w * 0.35, -h / 2 - wheelR * 0.5, sz * d * 0.35]} castShadow>
          <sphereGeometry args={[wheelR, 8, 8]} />
          <meshStandardMaterial color="#222" roughness={0.5} metalness={0.3} />
        </mesh>
      ))}
      {/* Latches */}
      {[-1, 1].map(side => (
        <mesh key={side} position={[side * w * 0.25, 0, -d / 2 - 0.005]} castShadow>
          <boxGeometry args={[latchSize * 2, latchSize, latchSize]} />
          <meshStandardMaterial color="#c0c0c0" roughness={0.3} metalness={0.8} />
        </mesh>
      ))}
      {/* Contents when open */}
      {isOpen && containerContents && (
        <group position={[0, -h * 0.05, 0]}>
          {containerContents.items?.map((item, i) => (
            <mesh key={i} position={item.offset} castShadow>
              {item.shape === 'sphere'
                ? <sphereGeometry args={[item.size[0] / 2, 10, 10]} />
                : item.shape === 'cylinder'
                  ? <cylinderGeometry args={[item.size[0] / 2, item.size[0] / 2, item.size[1], 10]} />
                  : <boxGeometry args={item.size} />
              }
              <meshStandardMaterial color={item.color} roughness={0.6} />
            </mesh>
          ))}
        </group>
      )}
    </group>
  );
}

function BedShape({ size, color, roughness, metalness }: { size: [number, number, number]; color: string; roughness: number; metalness: number }) {
  const [w, h, d] = size;
  const frameH = h * 0.3;
  const mattressH = h * 0.25;
  const headboardH = h * 0.6;
  const pillowW = w * 0.25;
  const pillowH = h * 0.1;
  const pillowD = d * 0.12;
  return (
    <group>
      {/* Frame */}
      <mesh position={[0, frameH / 2 - h / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[w, frameH, d]} />
        <meshStandardMaterial color="#8B6F47" roughness={0.7} metalness={0.1} />
      </mesh>
      {/* Mattress */}
      <mesh position={[0, frameH + mattressH / 2 - h / 2, 0]} castShadow receiveShadow>
        <boxGeometry args={[w * 0.95, mattressH, d * 0.95]} />
        <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
      </mesh>
      {/* Headboard */}
      <mesh position={[0, frameH + headboardH / 2 - h / 2, -d / 2 + 0.03]} castShadow>
        <boxGeometry args={[w, headboardH, 0.06]} />
        <meshStandardMaterial color="#6B4F37" roughness={0.7} metalness={0.1} />
      </mesh>
      {/* Pillows */}
      {[-1, 1].map(side => (
        <mesh key={side} position={[side * w * 0.22, frameH + mattressH + pillowH / 2 - h / 2, -d * 0.32]} castShadow>
          <boxGeometry args={[pillowW, pillowH, pillowD]} />
          <meshStandardMaterial color="#f0ece0" roughness={0.9} metalness={0} />
        </mesh>
      ))}
    </group>
  );
}

function CabinetShape({ size, color, roughness, metalness, isOpen, containerContents }: {
  size: [number, number, number]; color: string; roughness: number; metalness: number;
  isOpen?: boolean; containerContents?: ContainerContents;
}) {
  const [w, h, d] = size;
  const doorThick = 0.02;
  const shelfThick = 0.015;
  return (
    <group>
      {/* Body */}
      <mesh position={[0, 0, 0]} castShadow receiveShadow>
        <boxGeometry args={[w, h, d]} />
        <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
      </mesh>
      {/* Doors */}
      {[-1, 1].map(side => (
        <group key={side}
          position={[side * w * 0.25, 0, -d / 2 - doorThick / 2]}
          rotation={[0, isOpen ? side * Math.PI * 0.4 : 0, 0]}
        >
          <mesh castShadow>
            <boxGeometry args={[w * 0.48, h * 0.95, doorThick]} />
            <meshStandardMaterial color={color} roughness={roughness - 0.05} metalness={metalness} />
          </mesh>
          {/* Door handle */}
          <mesh position={[-side * w * 0.18, 0, -0.015]} castShadow>
            <sphereGeometry args={[0.015, 6, 6]} />
            <meshStandardMaterial color="#c0a050" roughness={0.3} metalness={0.8} />
          </mesh>
        </group>
      ))}
      {/* Shelves inside (visible when open) */}
      {isOpen && (
        <>
          <mesh position={[0, h * 0.15, 0]}>
            <boxGeometry args={[w * 0.9, shelfThick, d * 0.9]} />
            <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
          </mesh>
          <mesh position={[0, -h * 0.15, 0]}>
            <boxGeometry args={[w * 0.9, shelfThick, d * 0.9]} />
            <meshStandardMaterial color={color} roughness={roughness} metalness={metalness} />
          </mesh>
        </>
      )}
      {/* Contents when open */}
      {isOpen && containerContents && containerContents.items?.map((item, i) => (
        <mesh key={i} position={item.offset} castShadow>
          {item.shape === 'sphere'
            ? <sphereGeometry args={[item.size[0] / 2, 10, 10]} />
            : item.shape === 'cylinder'
              ? <cylinderGeometry args={[item.size[0] / 2, item.size[0] / 2, item.size[1], 10]} />
              : <boxGeometry args={item.size} />
          }
          <meshStandardMaterial color={item.color} roughness={0.6} />
        </mesh>
      ))}
    </group>
  );
}

function WindowShape({ size, color }: { size: [number, number, number]; color: string }) {
  const [w, h, d] = size;
  const frameW = w * 0.06;
  return (
    <group>
      {/* Frame */}
      {[
        [0, h / 2 - frameW / 2, 0, w, frameW, d],
        [0, -h / 2 + frameW / 2, 0, w, frameW, d],
        [-w / 2 + frameW / 2, 0, 0, frameW, h, d],
        [w / 2 - frameW / 2, 0, 0, frameW, h, d],
        [0, 0, 0, frameW, h, d], // center divider
      ].map(([px, py, pz, sx, sy, sz], i) => (
        <mesh key={i} position={[px as number, py as number, pz as number]} castShadow>
          <boxGeometry args={[sx as number, sy as number, sz as number]} />
          <meshStandardMaterial color={color || '#f5f0e8'} roughness={0.6} metalness={0.05} />
        </mesh>
      ))}
      {/* Glass pane */}
      <mesh position={[0, 0, 0]}>
        <planeGeometry args={[w - frameW * 2, h - frameW * 2]} />
        <meshStandardMaterial color="#b8d4e8" transparent opacity={0.3} roughness={0.1} metalness={0.2} side={THREE.DoubleSide} />
      </mesh>
    </group>
  );
}

function PictureShape({ size, color }: { size: [number, number, number]; color: string }) {
  const [w, h, d] = size;
  const frameW = w * 0.08;
  return (
    <group>
      {/* Frame border */}
      <mesh position={[0, 0, 0]} castShadow>
        <boxGeometry args={[w, h, d || 0.03]} />
        <meshStandardMaterial color="#5a3a1a" roughness={0.6} metalness={0.1} />
      </mesh>
      {/* Inner picture */}
      <mesh position={[0, 0, -(d || 0.03) / 2 - 0.001]}>
        <planeGeometry args={[w - frameW * 2, h - frameW * 2]} />
        <meshStandardMaterial color={color} roughness={0.4} />
      </mesh>
    </group>
  );
}

function PlantShape({ size, color }: { size: [number, number, number]; color: string }) {
  const [w, h] = size;
  const potH = h * 0.35;
  const potR = w * 0.35;
  const foliageR = w * 0.45;
  return (
    <group>
      {/* Pot */}
      <mesh position={[0, -h / 2 + potH / 2, 0]} castShadow receiveShadow>
        <cylinderGeometry args={[potR * 0.8, potR, potH, 12]} />
        <meshStandardMaterial color="#8B5E3C" roughness={0.7} metalness={0.1} />
      </mesh>
      {/* Soil */}
      <mesh position={[0, -h / 2 + potH - 0.01, 0]}>
        <cylinderGeometry args={[potR * 0.75, potR * 0.75, 0.02, 12]} />
        <meshStandardMaterial color="#3a2a1a" roughness={0.9} />
      </mesh>
      {/* Foliage cluster */}
      <mesh position={[0, h * 0.1, 0]} castShadow>
        <sphereGeometry args={[foliageR, 12, 12]} />
        <meshStandardMaterial color={color || '#2d5a1e'} roughness={0.8} />
      </mesh>
      {[-0.6, 0.6].map(ox => (
        <mesh key={ox} position={[ox * foliageR, h * 0.05, 0]} castShadow>
          <sphereGeometry args={[foliageR * 0.65, 10, 10]} />
          <meshStandardMaterial color={color || '#3a7a2a'} roughness={0.8} />
        </mesh>
      ))}
      <mesh position={[0, h * 0.05, -0.5 * foliageR]} castShadow>
        <sphereGeometry args={[foliageR * 0.55, 10, 10]} />
        <meshStandardMaterial color={color || '#1e4a16'} roughness={0.8} />
      </mesh>
    </group>
  );
}

export default function PBRObject({ obj, activeInteraction, doorReveal, containerContents, objectDetails }: PBRObjectProps) {
  const rotation = obj.rotation
    ? obj.rotation.map((r) => (r * Math.PI) / 180) as [number, number, number]
    : [0, 0, 0] as [number, number, number];

  const interaction = obj.interaction && obj.interaction !== 'none'
    ? obj.interaction
    : guessInteraction(obj.name);

  const isActive = activeInteraction?.objectName === obj.name;
  const objType = guessObjectType(obj.name);
  const isOpen = isActive && activeInteraction?.type === 'open';

  let emissive = '#000000';
  let emissiveIntensity = 0;

  if (isActive) {
    switch (activeInteraction?.type) {
      case 'use':
        emissive = '#4488ff';
        emissiveIntensity = 0.4;
        break;
      case 'toggle':
        emissive = '#ffee44';
        emissiveIntensity = 0.6;
        break;
    }
  }

  const matProps = {
    color: obj.color,
    roughness: obj.roughness ?? 0.5,
    metalness: obj.metalness ?? 0.1,
  };

  const compositeTypes = ['table', 'chair', 'monitor', 'lamp', 'couch', 'shelf', 'door', 'suitcase', 'bed', 'cabinet', 'window', 'picture', 'plant'];
  const useComposite = obj.shape === 'box';
  const isComposite = useComposite && compositeTypes.includes(objType);

  const renderComposite = () => {
    switch (objType) {
      case 'table': return <TableShape size={obj.size} {...matProps} />;
      case 'chair': return <ChairShape size={obj.size} {...matProps} />;
      case 'monitor': return <MonitorShape size={obj.size} {...matProps} />;
      case 'lamp': return <LampShape size={obj.size} {...matProps} />;
      case 'couch': return <CouchShape size={obj.size} {...matProps} />;
      case 'shelf': return <ShelfShape size={obj.size} {...matProps} />;
      case 'door': return <DoorShape size={obj.size} {...matProps} isOpen={isOpen} doorReveal={doorReveal} />;
      case 'suitcase': return <SuitcaseShape size={obj.size} {...matProps} isOpen={isOpen} containerContents={containerContents} />;
      case 'bed': return <BedShape size={obj.size} {...matProps} />;
      case 'cabinet': return <CabinetShape size={obj.size} {...matProps} isOpen={isOpen} containerContents={containerContents} />;
      case 'window': return <WindowShape size={obj.size} color={obj.color} />;
      case 'picture': return <PictureShape size={obj.size} color={obj.color} />;
      case 'plant': return <PlantShape size={obj.size} color={obj.color} />;
      default: return null;
    }
  };

  return (
    <group position={obj.position} rotation={rotation}>
      {isComposite ? renderComposite() : (
        <mesh castShadow receiveShadow>
          {getGeometry(obj.shape, obj.size)}
          <meshStandardMaterial
            color={obj.color}
            roughness={obj.roughness ?? 0.5}
            metalness={obj.metalness ?? 0.1}
            side={obj.shape === 'plane' ? THREE.DoubleSide : THREE.FrontSide}
            emissive={emissive}
            emissiveIntensity={emissiveIntensity}
          />
        </mesh>
      )}

      {/* Whiteboard text overlay */}
      {isActive && activeInteraction?.type === 'write' && (
        <Html
          position={[0, obj.size[1] * 0.15, obj.size[2] / 2 + 0.01]}
          transform
          occlude
          style={{ pointerEvents: 'none' }}
        >
          <div style={{
            background: 'rgba(255,255,255,0.9)',
            padding: '8px 16px',
            borderRadius: 4,
            fontFamily: 'cursive',
            fontSize: 14,
            color: '#222',
            whiteSpace: 'nowrap',
          }}>
            Hello World!
          </div>
        </Html>
      )}

      {/* Screen ON indicator */}
      {isActive && activeInteraction?.type === 'use' && (
        <mesh position={[0, 0, obj.size[2] / 2 + 0.005]}>
          <planeGeometry args={[obj.size[0] * 0.8, obj.size[1] * 0.6]} />
          <meshBasicMaterial color="#1a2a4a" transparent opacity={0.85} />
        </mesh>
      )}

      {/* Light when toggled */}
      {isActive && activeInteraction?.type === 'toggle' && (
        <pointLight color="#ffee88" intensity={2} distance={5} />
      )}

      {obj.children?.map((child, i) => (
        <PBRObject key={`${obj.name}-child-${i}`} obj={child} activeInteraction={activeInteraction} />
      ))}
    </group>
  );
}
