'use client';

import { useRef, useEffect, useCallback, useMemo } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { SceneObject, ScenePerson, InteractionType } from '@/lib/api';

const MOVE_SPEED = 3.5;
const MOUSE_SENSITIVITY = 0.002;
const PREFERRED_CAM_DISTANCE = 2.0;
const MIN_CAM_DISTANCE = 0.4;
const CAM_HEIGHT_OFFSET = 1.0;
const LOOK_AT_HEIGHT = 1.3;
const MIN_POLAR = 0.4;
const MAX_POLAR = Math.PI * 0.45;
const GRAVITY = -9.8;
const PLAYER_RADIUS = 0.3;
const PLAYER_HEIGHT = 1.7;

const WALL_NEAR = 1.2;
const WALL_VERY_NEAR = 0.5;
const OBJ_NEAR = 1.8;
const INTERACT_RANGE = 1.5;
const PERSON_NEAR = 2.0;
const PERSON_INTERACT = 1.2;

const SIT_LERP_SPEED = 4.0;
const GREET_LERP_SPEED = 5.0;

// Guess interaction from name if not provided by scene JSON
function guessInteraction(name: string | null | undefined): InteractionType {
  const n = String(name ?? '').toLowerCase();
  if (/chair|couch|sofa|bench|stool|seat/.test(n)) return 'sit';
  if (/whiteboard|blackboard|chalkboard|board/.test(n)) return 'write';
  if (/laptop|monitor|computer|tv|television|microwave|printer|phone|coffee|machine|screen/.test(n)) return 'use';
  if (/door|cabinet|drawer|fridge|closet|cupboard|suitcase/.test(n)) return 'open';
  if (/lamp|light|switch|fan/.test(n)) return 'toggle';
  return 'none';
}

const INTERACTION_LABELS: Record<InteractionType, string> = {
  none: '',
  sit: 'Sit down',
  write: 'Write on it',
  use: 'Use device',
  open: 'Open',
  toggle: 'Toggle on/off',
};

function safeInteractionTargetName(name: string | null | undefined, fallback = 'object'): string {
  const cleaned = String(name ?? '').trim();
  return cleaned || fallback;
}

function humanizeTargetName(name: string | null | undefined, fallback = 'object'): string {
  return safeInteractionTargetName(name, fallback).replace(/_/g, ' ');
}

export interface InteractionPrompt {
  objectName: string;
  action: string;
  interactionType: InteractionType;
}

export interface ActiveInteraction {
  type: InteractionType;
  objectName: string;
  personName?: string;
}

interface FlatObj {
  name: string;
  worldPos: THREE.Vector3;
  size: THREE.Vector3;
  interaction: InteractionType;
  rotation?: [number, number, number];
}

interface AABB {
  name: string;
  minX: number;
  maxX: number;
  minZ: number;
  maxZ: number;
  interaction: InteractionType;
}

function flattenObjects(objects: SceneObject[], parentPos: [number, number, number] = [0, 0, 0]): FlatObj[] {
  const result: FlatObj[] = [];
  for (const obj of objects) {
    const wp = new THREE.Vector3(
      parentPos[0] + obj.position[0],
      parentPos[1] + obj.position[1],
      parentPos[2] + obj.position[2]
    );
    const interaction = obj.interaction && obj.interaction !== 'none'
      ? obj.interaction
      : guessInteraction(obj.name);
    result.push({ name: obj.name, worldPos: wp, size: new THREE.Vector3(...obj.size), interaction, rotation: obj.rotation });
    if (obj.children) {
      result.push(...flattenObjects(obj.children, [wp.x, wp.y, wp.z]));
    }
  }
  return result;
}

function buildAABBs(flatObjs: FlatObj[], people: ScenePerson[] | undefined): AABB[] {
  const aabbs: AABB[] = [];

  for (const obj of flatObjs) {
    // Skip planes, very thin objects (<0.05m in both XZ), and ceiling-mounted items
    if (obj.size.x < 0.05 && obj.size.z < 0.05) continue;
    if (obj.worldPos.y - obj.size.y / 2 > 1.5) continue; // ceiling mounted
    if (obj.size.y < 0.02) continue; // flat plane like rug

    // Account for rotation (simple Y-axis rotation for AABB)
    let hw = obj.size.x / 2;
    let hd = obj.size.z / 2;
    if (obj.rotation) {
      const ry = (obj.rotation[1] * Math.PI) / 180;
      const cos = Math.abs(Math.cos(ry));
      const sin = Math.abs(Math.sin(ry));
      const nhw = hw * cos + hd * sin;
      const nhd = hw * sin + hd * cos;
      hw = nhw;
      hd = nhd;
    }

    aabbs.push({
      name: obj.name,
      minX: obj.worldPos.x - hw,
      maxX: obj.worldPos.x + hw,
      minZ: obj.worldPos.z - hd,
      maxZ: obj.worldPos.z + hd,
      interaction: obj.interaction,
    });
  }

  // Add people as small colliders
  if (people) {
    for (const p of people) {
      const r = 0.2;
      aabbs.push({
        name: p.name,
        minX: p.position[0] - r,
        maxX: p.position[0] + r,
        minZ: p.position[2] - r,
        maxZ: p.position[2] + r,
        interaction: 'none',
      });
    }
  }

  return aabbs;
}

export interface MissionEvent {
  type: InteractionType | 'greet' | 'corner';
  targetName: string;
}

export interface ThirdPersonControllerProps {
  roomBounds?: { halfW: number; halfD: number; height: number };
  objects?: SceneObject[];
  people?: ScenePerson[];
  onCommentary?: (lines: string[]) => void;
  onInteractionPrompt?: (prompt: InteractionPrompt | null) => void;
  onActiveInteraction?: (interaction: ActiveInteraction | null) => void;
  onPlayerPosition?: (pos: [number, number, number]) => void;
  onMissionEvent?: (event: MissionEvent) => void;
  openDoors?: Set<string>;
}

export default function ThirdPersonController({
  roomBounds, objects, people, onCommentary, onInteractionPrompt, onActiveInteraction, onPlayerPosition, onMissionEvent, openDoors,
}: ThirdPersonControllerProps) {
  const { gl, camera } = useThree();
  const playerRef = useRef<THREE.Group>(null!);
  const keysRef = useRef<Set<string>>(new Set());
  const yawRef = useRef(0);
  const pitchRef = useRef(0.8);
  const isLockedRef = useRef(false);
  const velocityYRef = useRef(0);
  const lastCommentaryRef = useRef('');
  const commentaryTimerRef = useRef(0);

  // Interaction state
  const activeInteractionRef = useRef<ActiveInteraction | null>(null);
  const currentPromptRef = useRef<string>('');
  const justPressedERef = useRef(false);

  // Smooth sit/greet lerp
  const sitProgressRef = useRef(0);
  const sitTargetRef = useRef<THREE.Vector3 | null>(null);
  const greetProgressRef = useRef(0);
  const greetTargetFacingRef = useRef(0);

  const flatObjsRef = useRef<FlatObj[]>([]);
  const aabbsRef = useRef<AABB[]>([]);
  const visitedCornersRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const flat = objects ? flattenObjects(objects) : [];
    flatObjsRef.current = flat;
    aabbsRef.current = buildAABBs(flat, people);
  }, [objects, people]);

  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    keysRef.current.add(e.code);
    if (e.code === 'KeyE') justPressedERef.current = true;
  }, []);

  const handleKeyUp = useCallback((e: KeyboardEvent) => {
    keysRef.current.delete(e.code);
  }, []);

  const handleMouseMove = useCallback((e: MouseEvent) => {
    if (!isLockedRef.current) return;
    yawRef.current -= e.movementX * MOUSE_SENSITIVITY;
    pitchRef.current = Math.max(MIN_POLAR, Math.min(MAX_POLAR, pitchRef.current + e.movementY * MOUSE_SENSITIVITY));
  }, []);

  const handleClick = useCallback(() => {
    gl.domElement.requestPointerLock();
  }, [gl]);

  useEffect(() => {
    const canvas = gl.domElement;
    const handleLockChange = () => { isLockedRef.current = document.pointerLockElement === canvas; };
    document.addEventListener('keydown', handleKeyDown);
    document.addEventListener('keyup', handleKeyUp);
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('pointerlockchange', handleLockChange);
    canvas.addEventListener('click', handleClick);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.removeEventListener('keyup', handleKeyUp);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('pointerlockchange', handleLockChange);
      canvas.removeEventListener('click', handleClick);
    };
  }, [gl, handleKeyDown, handleKeyUp, handleMouseMove, handleClick]);

  useFrame((_, delta) => {
    if (!playerRef.current) return;
    const dt = Math.min(delta, 0.05);
    const keys = keysRef.current;
    const pos = playerRef.current.position;
    const ePressed = justPressedERef.current;
    justPressedERef.current = false;

    const isSitting = activeInteractionRef.current?.type === 'sit';
    const isGreeting = activeInteractionRef.current?.personName != null;

    // --- Smooth sit lerp ---
    if (isSitting && sitTargetRef.current) {
      sitProgressRef.current = Math.min(1, sitProgressRef.current + SIT_LERP_SPEED * dt);
      pos.x = THREE.MathUtils.lerp(pos.x, sitTargetRef.current.x, sitProgressRef.current);
      pos.z = THREE.MathUtils.lerp(pos.z, sitTargetRef.current.z, sitProgressRef.current);
    }

    // --- Smooth greet facing ---
    if (isGreeting) {
      greetProgressRef.current = Math.min(1, greetProgressRef.current + GREET_LERP_SPEED * dt);
      let diff = greetTargetFacingRef.current - playerRef.current.rotation.y;
      while (diff > Math.PI) diff -= 2 * Math.PI;
      while (diff < -Math.PI) diff += 2 * Math.PI;
      playerRef.current.rotation.y += diff * greetProgressRef.current * dt * 5;
    } else {
      greetProgressRef.current = Math.max(0, greetProgressRef.current - GREET_LERP_SPEED * dt);
    }

    // --- Movement (disabled while sitting) ---
    const isMoving = !isSitting && (keys.has('KeyW') || keys.has('KeyS') || keys.has('KeyA') || keys.has('KeyD'));
    const moveDir = new THREE.Vector3();

    if (!isSitting) {
      if (keys.has('KeyW')) moveDir.z -= 1;
      if (keys.has('KeyS')) moveDir.z += 1;
      if (keys.has('KeyA')) moveDir.x -= 1;
      if (keys.has('KeyD')) moveDir.x += 1;

      if (moveDir.lengthSq() > 0) {
        moveDir.normalize();
        moveDir.applyAxisAngle(new THREE.Vector3(0, 1, 0), yawRef.current);
        pos.x += moveDir.x * MOVE_SPEED * dt;
        pos.z += moveDir.z * MOVE_SPEED * dt;
        const targetAngle = Math.atan2(moveDir.x, moveDir.z);
        let diff = targetAngle - playerRef.current.rotation.y;
        while (diff > Math.PI) diff -= 2 * Math.PI;
        while (diff < -Math.PI) diff += 2 * Math.PI;
        playerRef.current.rotation.y += diff * Math.min(1, 10 * dt);
      }
    }

    // Stand up when moving while sitting
    if (isSitting && (keys.has('KeyW') || keys.has('KeyS') || keys.has('KeyA') || keys.has('KeyD'))) {
      activeInteractionRef.current = null;
      sitProgressRef.current = 0;
      sitTargetRef.current = null;
      onActiveInteraction?.(null);
    }

    // --- AABB Collision ---
    if (!isSitting) {
      const pr = PLAYER_RADIUS;
      const pMinX = pos.x - pr;
      const pMaxX = pos.x + pr;
      const pMinZ = pos.z - pr;
      const pMaxZ = pos.z + pr;

      for (const aabb of aabbsRef.current) {
        // Skip open doors
        if (openDoors?.has(aabb.name) && aabb.interaction === 'open') continue;

        // Check overlap
        if (pMaxX > aabb.minX && pMinX < aabb.maxX && pMaxZ > aabb.minZ && pMinZ < aabb.maxZ) {
          // Push out along axis of least penetration
          const overlapLeft = pMaxX - aabb.minX;
          const overlapRight = aabb.maxX - pMinX;
          const overlapFront = pMaxZ - aabb.minZ;
          const overlapBack = aabb.maxZ - pMinZ;
          const minOverlap = Math.min(overlapLeft, overlapRight, overlapFront, overlapBack);

          if (minOverlap === overlapLeft) pos.x -= overlapLeft;
          else if (minOverlap === overlapRight) pos.x += overlapRight;
          else if (minOverlap === overlapFront) pos.z -= overlapFront;
          else pos.z += overlapBack;
        }
      }
    }

    // --- Gravity + Jump ---
    if (!isSitting) {
      const onGround = pos.y <= 0.001;
      if (keys.has('Space') && onGround) velocityYRef.current = 4.5;
      velocityYRef.current += GRAVITY * dt;
      pos.y += velocityYRef.current * dt;
      if (pos.y < 0) { pos.y = 0; velocityYRef.current = 0; }
    }

    // --- Clamp bounds ---
    if (roomBounds) {
      const margin = PLAYER_RADIUS;
      pos.x = Math.max(-roomBounds.halfW + margin, Math.min(roomBounds.halfW - margin, pos.x));
      pos.z = Math.max(-roomBounds.halfD + margin, Math.min(roomBounds.halfD - margin, pos.z));
      if (pos.y + PLAYER_HEIGHT > roomBounds.height) {
        pos.y = roomBounds.height - PLAYER_HEIGHT;
        velocityYRef.current = 0;
      }
    }

    // --- Report player position ---
    onPlayerPosition?.([pos.x, pos.y, pos.z]);

    // --- Camera ---
    const rawOffset = new THREE.Vector3(
      PREFERRED_CAM_DISTANCE * Math.sin(pitchRef.current) * Math.sin(yawRef.current),
      PREFERRED_CAM_DISTANCE * Math.cos(pitchRef.current) + CAM_HEIGHT_OFFSET,
      PREFERRED_CAM_DISTANCE * Math.sin(pitchRef.current) * Math.cos(yawRef.current)
    );
    const camTarget = new THREE.Vector3().copy(pos).add(rawOffset);
    if (roomBounds) {
      const cm = 0.15;
      camTarget.x = Math.max(-roomBounds.halfW + cm, Math.min(roomBounds.halfW - cm, camTarget.x));
      camTarget.y = Math.max(0.3, Math.min(roomBounds.height - cm, camTarget.y));
      camTarget.z = Math.max(-roomBounds.halfD + cm, Math.min(roomBounds.halfD - cm, camTarget.z));
      if (camTarget.distanceTo(pos) < MIN_CAM_DISTANCE) {
        camTarget.set(pos.x, Math.min(pos.y + CAM_HEIGHT_OFFSET + 0.5, roomBounds.height - cm), pos.z);
      }
    }
    camera.position.lerp(camTarget, Math.min(1, 8 * dt));
    camera.lookAt(pos.x, pos.y + LOOK_AT_HEIGHT, pos.z);

    // --- Interaction detection ---
    const playerXZ = new THREE.Vector2(pos.x, pos.z);
    let closestInteractable: { name: string; dist: number; interaction: InteractionType; pos: THREE.Vector3 } | null = null;
    let closestPerson: { name: string; dist: number; pos: [number, number, number] } | null = null;

    // Objects
    for (const obj of flatObjsRef.current) {
      if (obj.interaction === 'none') continue;
      const dist = playerXZ.distanceTo(new THREE.Vector2(obj.worldPos.x, obj.worldPos.z));
      if (dist < INTERACT_RANGE && (!closestInteractable || dist < closestInteractable.dist)) {
        closestInteractable = { name: obj.name, dist, interaction: obj.interaction, pos: obj.worldPos };
      }
    }

    // People
    if (people) {
      for (const p of people) {
        const dist = playerXZ.distanceTo(new THREE.Vector2(p.position[0], p.position[2]));
        if (dist < PERSON_INTERACT && (!closestPerson || dist < closestPerson.dist)) {
          closestPerson = { name: p.name, dist, pos: p.position };
        }
      }
    }

    // Determine prompt
    let newPrompt = '';
    if (activeInteractionRef.current) {
      const ai = activeInteractionRef.current;
      const targetName = humanizeTargetName(ai.objectName, ai.personName || 'object');
      if (ai.type === 'sit') newPrompt = `__active__Sitting on ${targetName} — WASD to stand up`;
      else if (ai.type === 'write') newPrompt = `__active__Writing on ${targetName} — Press E to stop`;
      else if (ai.type === 'use') newPrompt = `__active__Using ${targetName} — Press E to stop`;
      else if (ai.type === 'open') newPrompt = `__active__${targetName} is open — Press E to close`;
      else if (ai.type === 'toggle') newPrompt = `__active__${targetName} toggled — Press E again`;
      else if (ai.personName) newPrompt = `__active__Greeting ${humanizeTargetName(ai.personName, 'person')} — Press E to stop`;
    } else if (closestPerson) {
      newPrompt = `${closestPerson.name}|greet|Press E to greet ${closestPerson.name.replace(/_/g, ' ')}`;
    } else if (closestInteractable) {
      const label = INTERACTION_LABELS[closestInteractable.interaction];
      newPrompt = `${closestInteractable.name}|${closestInteractable.interaction}|Press E — ${label} (${closestInteractable.name.replace(/_/g, ' ')})`;
    }

    if (newPrompt !== currentPromptRef.current) {
      currentPromptRef.current = newPrompt;
      if (newPrompt.startsWith('__active__')) {
        onInteractionPrompt?.({ objectName: '', action: newPrompt.slice(9), interactionType: 'none' });
      } else if (newPrompt) {
        const parts = newPrompt.split('|');
        const objName = safeInteractionTargetName(parts[0], 'object');
        const iTypeRaw = (parts[1] || 'none') as InteractionType;
        const action = parts.slice(2).join('|') || 'Interact';
        const interactionType: InteractionType = ['none', 'sit', 'write', 'use', 'open', 'toggle'].includes(iTypeRaw)
          ? iTypeRaw
          : 'none';
        onInteractionPrompt?.({ objectName: objName, action, interactionType });
      } else {
        onInteractionPrompt?.(null);
      }
    }

    // Handle E press
    if (ePressed) {
      if (activeInteractionRef.current) {
        // Toggle off (except sit which uses WASD)
        if (activeInteractionRef.current.type !== 'sit') {
          activeInteractionRef.current = null;
          greetProgressRef.current = 0;
          onActiveInteraction?.(null);
        }
      } else if (closestPerson) {
        // Greeting: face towards person
        const dx = closestPerson.pos[0] - pos.x;
        const dz = closestPerson.pos[2] - pos.z;
        greetTargetFacingRef.current = Math.atan2(dx, dz);
        greetProgressRef.current = 0;
        const personName = safeInteractionTargetName(closestPerson.name, 'person');
        const ai: ActiveInteraction = { type: 'none' as InteractionType, objectName: personName, personName };
        activeInteractionRef.current = ai;
        onActiveInteraction?.(ai);
        onMissionEvent?.({ type: 'greet', targetName: closestPerson.name });
      } else if (closestInteractable) {
        if (closestInteractable.interaction === 'sit') {
          // Smooth sit: lerp to chair position
          sitTargetRef.current = closestInteractable.pos.clone();
          sitProgressRef.current = 0;
        }
        const ai: ActiveInteraction = {
          type: closestInteractable.interaction,
          objectName: safeInteractionTargetName(closestInteractable.name),
        };
        activeInteractionRef.current = ai;
        onActiveInteraction?.(ai);
        onMissionEvent?.({ type: closestInteractable.interaction, targetName: closestInteractable.name });
      }
    }

    // --- Corner visit detection for missions ---
    if (roomBounds) {
      const cornerThreshold = 1.2;
      const corners: [string, number, number][] = [
        ['front-left', -roomBounds.halfW, -roomBounds.halfD],
        ['front-right', roomBounds.halfW, -roomBounds.halfD],
        ['back-left', -roomBounds.halfW, roomBounds.halfD],
        ['back-right', roomBounds.halfW, roomBounds.halfD],
      ];
      for (const [name, cx, cz] of corners) {
        if (!visitedCornersRef.current.has(name)) {
          const dist = Math.sqrt((pos.x - cx) ** 2 + (pos.z - cz) ** 2);
          if (dist < cornerThreshold) {
            visitedCornersRef.current.add(name);
            onMissionEvent?.({ type: 'corner', targetName: name });
          }
        }
      }
    }

    // --- Commentary (throttled, max 2 lines, prioritized) ---
    commentaryTimerRef.current += dt;
    if (onCommentary && commentaryTimerRef.current > 0.4) {
      commentaryTimerRef.current = 0;
      const candidates: { text: string; priority: number }[] = [];
      const isJumping = pos.y > 0.01;

      if (isSitting) {
        candidates.push({ text: `Sitting on ${humanizeTargetName(activeInteractionRef.current?.objectName)}`, priority: 1 });
      }
      if (isJumping && velocityYRef.current > 0) candidates.push({ text: 'Jumping', priority: 1 });
      else if (isJumping && velocityYRef.current < -2) candidates.push({ text: 'Falling', priority: 1 });

      if (people) {
        const closestP = people
          .map(p => ({ name: p.name.replace(/_/g, ' '), pose: p.pose, dist: playerXZ.distanceTo(new THREE.Vector2(p.position[0], p.position[2])) }))
          .filter(p => p.dist < PERSON_NEAR)
          .sort((a, b) => a.dist - b.dist)[0];
        if (closestP) {
          const txt = closestP.dist < 0.8 ? `Standing beside ${closestP.name}` : `Near ${closestP.name}`;
          candidates.push({ text: txt, priority: 2 });
        }
      }

      const nearby = flatObjsRef.current
        .map(o => ({ name: o.name.replace(/_/g, ' '), dist: playerXZ.distanceTo(new THREE.Vector2(o.worldPos.x, o.worldPos.z)), dx: o.worldPos.x - pos.x, dz: o.worldPos.z - pos.z }))
        .filter(o => o.dist < OBJ_NEAR)
        .sort((a, b) => a.dist - b.dist);
      if (nearby[0]) {
        const obj = nearby[0];
        const txt = obj.dist < 0.8 ? `Right next to the ${obj.name}` : `Near the ${obj.name}`;
        candidates.push({ text: txt, priority: 3 });
      }

      if (roomBounds) {
        const dFront = Math.abs(pos.z + roomBounds.halfD);
        const dBack = Math.abs(pos.z - roomBounds.halfD);
        const dLeft = Math.abs(pos.x + roomBounds.halfW);
        const dRight = Math.abs(pos.x - roomBounds.halfW);
        const walls = [
          { name: 'front wall', dist: dFront }, { name: 'back wall', dist: dBack },
          { name: 'left wall', dist: dLeft }, { name: 'right wall', dist: dRight },
        ];
        const nearWalls = walls.filter(w => w.dist < WALL_NEAR);
        if (nearWalls.length >= 2) {
          candidates.push({ text: `In the ${nearWalls.map(w => w.name.replace(' wall', '')).join('-')} corner`, priority: 4 });
        } else if (nearWalls.length === 1) {
          const w = nearWalls[0];
          candidates.push({ text: w.dist < WALL_VERY_NEAR ? `Right against the ${w.name}` : `Near the ${w.name}`, priority: 5 });
        } else if (!isMoving && !isJumping && walls.every(w => w.dist > Math.min(roomBounds.halfW, roomBounds.halfD) * 0.5)) {
          candidates.push({ text: 'In the center of the room', priority: 6 });
        }
      }

      if (isMoving && candidates.length === 0) {
        const angle = Math.atan2(moveDir.x, moveDir.z);
        let d = 'forward';
        if (angle > -Math.PI / 4 && angle <= Math.PI / 4) d = 'toward the back wall';
        else if (angle > Math.PI / 4 && angle <= 3 * Math.PI / 4) d = 'toward the right wall';
        else if (angle > -3 * Math.PI / 4 && angle <= -Math.PI / 4) d = 'toward the left wall';
        else d = 'toward the front wall';
        candidates.push({ text: `Walking ${d}`, priority: 7 });
      }

      candidates.sort((a, b) => a.priority - b.priority);
      const lines = candidates.slice(0, 2).map(c => c.text);

      const joined = lines.join(' | ');
      if (joined !== lastCommentaryRef.current) {
        lastCommentaryRef.current = joined;
        onCommentary(lines);
      }
    }
  });

  const s = PLAYER_HEIGHT / 1.75;
  const isSitting = activeInteractionRef.current?.type === 'sit';
  const isGreeting = activeInteractionRef.current?.personName != null;
  const headY_p = isSitting ? 1.15 * s : 1.62 * s;
  const headR_p = 0.09 * s;

  return (
    <group ref={playerRef} position={[0, 0, 0]}>
      {/* Head */}
      <mesh position={[0, headY_p, 0]} castShadow>
        <sphereGeometry args={[headR_p, 16, 16]} />
        <meshStandardMaterial color="#ffccaa" roughness={0.7} />
      </mesh>

      {/* === Player Facial Features === */}
      {/* Eyes */}
      {[-1, 1].map(side => (
        <group key={`peye${side}`}>
          <mesh position={[side * 0.03 * s, headY_p + 0.01 * s, -headR_p * 0.85]}>
            <sphereGeometry args={[0.015 * s, 8, 8]} />
            <meshStandardMaterial color="#f8f8f0" roughness={0.3} />
          </mesh>
          <mesh position={[side * 0.03 * s, headY_p + 0.01 * s, -headR_p * 0.95]}>
            <sphereGeometry args={[0.008 * s, 8, 8]} />
            <meshStandardMaterial color="#4a6a20" roughness={0.4} />
          </mesh>
          <mesh position={[side * 0.03 * s, headY_p + 0.01 * s, -headR_p * 0.99]}>
            <sphereGeometry args={[0.004 * s, 6, 6]} />
            <meshStandardMaterial color="#111111" roughness={0.2} />
          </mesh>
          <mesh position={[side * 0.03 * s, headY_p + 0.04 * s, -headR_p * 0.82]}>
            <boxGeometry args={[0.035 * s, 0.006 * s, 0.01 * s]} />
            <meshStandardMaterial color="#5a3a1a" roughness={0.8} />
          </mesh>
        </group>
      ))}
      {/* Nose */}
      <mesh position={[0, headY_p - 0.01 * s, -headR_p * 0.92]}>
        <sphereGeometry args={[0.012 * s, 8, 8]} />
        <meshStandardMaterial color="#ffccaa" roughness={0.7} />
      </mesh>
      {/* Mouth */}
      <mesh position={[0, headY_p - 0.035 * s, -headR_p * 0.88]} scale={[1.5, 0.4, 0.8]}>
        <sphereGeometry args={[0.012 * s, 8, 8]} />
        <meshStandardMaterial color="#a85050" roughness={0.6} />
      </mesh>
      {/* Ears */}
      {[-1, 1].map(side => (
        <mesh key={`pear${side}`} position={[side * headR_p * 0.92, headY_p, 0]}>
          <sphereGeometry args={[0.018 * s, 6, 6]} />
          <meshStandardMaterial color="#ffccaa" roughness={0.7} />
        </mesh>
      ))}
      {/* Short brown hair */}
      <mesh position={[0, headY_p + headR_p * 0.55, -headR_p * 0.1]}>
        <sphereGeometry args={[headR_p * 0.95, 16, 16, 0, Math.PI * 2, 0, Math.PI * 0.55]} />
        <meshStandardMaterial color="#5a3a1a" roughness={0.9} />
      </mesh>

      {/* Neck */}
      <mesh position={[0, isSitting ? 1.06 * s : 1.53 * s, 0]} castShadow>
        <cylinderGeometry args={[0.035 * s, 0.04 * s, 0.06 * s, 8]} />
        <meshStandardMaterial color="#ffccaa" roughness={0.7} />
      </mesh>

      {/* Upper Torso (wider V-shape) */}
      <mesh position={[0, isSitting ? 0.88 * s : 1.30 * s, 0]} castShadow>
        <boxGeometry args={[0.39 * s, 0.27 * s, 0.21 * s]} />
        <meshStandardMaterial color="#eeeeee" roughness={0.5} />
      </mesh>
      {/* Lower Torso (narrower) */}
      <mesh position={[0, isSitting ? 0.65 * s : 1.07 * s, 0]} castShadow>
        <boxGeometry args={[0.32 * s, 0.24 * s, 0.185 * s]} />
        <meshStandardMaterial color="#eeeeee" roughness={0.5} />
      </mesh>
      {/* Collar */}
      <mesh position={[0, isSitting ? 0.98 * s : 1.40 * s, -0.07 * s]} castShadow>
        <boxGeometry args={[0.32 * s, 0.04 * s, 0.06 * s]} />
        <meshStandardMaterial color="#eeeeee" roughness={0.5} />
      </mesh>

      {/* Hips */}
      <mesh position={[0, isSitting ? 0.5 * s : 0.90 * s, 0]} castShadow>
        <boxGeometry args={[0.32 * s, 0.1 * s, 0.19 * s]} />
        <meshStandardMaterial color="#2a2a3a" roughness={0.7} />
      </mesh>

      {/* Arms with slight outward angle */}
      {[-1, 1].map(side => {
        const shoulderY_p = isSitting ? 0.98 * s : 1.42 * s;
        const armAngle = side === 1 && isGreeting ? 0 : (side * -0.12);
        const armPitch = side === 1 && isGreeting ? Math.PI * 0.4 : 0;
        return (
          <group key={`arm${side}`}>
            {/* Shoulder */}
            <mesh position={[side * 0.2 * s, shoulderY_p, 0]} castShadow>
              <sphereGeometry args={[0.045 * s, 8, 8]} />
              <meshStandardMaterial color="#eeeeee" roughness={0.5} />
            </mesh>
            <group position={[side * 0.2 * s, shoulderY_p, 0]} rotation={[armPitch, 0, armAngle]}>
              {/* Upper arm */}
              <mesh position={[0, -0.12 * s, 0]} castShadow>
                <capsuleGeometry args={[0.04 * s, 0.22 * s, 4, 8]} />
                <meshStandardMaterial color="#eeeeee" roughness={0.5} />
              </mesh>
              {/* Forearm */}
              <mesh position={[0, -0.36 * s, 0]} castShadow>
                <capsuleGeometry args={[0.032 * s, 0.2 * s, 4, 8]} />
                <meshStandardMaterial color="#ffccaa" roughness={0.7} />
              </mesh>
              {/* Hand (flattened mitten) */}
              <mesh position={[0, -0.5 * s, 0]} scale={[1, 0.7, 0.5]} castShadow>
                <sphereGeometry args={[0.035 * s, 6, 6]} />
                <meshStandardMaterial color="#ffccaa" roughness={0.7} />
              </mesh>
            </group>
          </group>
        );
      })}

      {/* Legs */}
      {[-1, 1].map(side => (
        <group key={`leg${side}`}>
          {isSitting ? (
            <>
              <mesh position={[side * 0.08 * s, 0.45 * s, 0.18 * s]} rotation={[Math.PI / 2, 0, 0]} castShadow>
                <capsuleGeometry args={[0.055 * s, 0.34 * s, 4, 8]} />
                <meshStandardMaterial color="#2a2a3a" roughness={0.7} />
              </mesh>
              <mesh position={[side * 0.08 * s, 0.15 * s, 0.36 * s]} castShadow>
                <capsuleGeometry args={[0.045 * s, 0.32 * s, 4, 8]} />
                <meshStandardMaterial color="#2a2a3a" roughness={0.7} />
              </mesh>
              <mesh position={[side * 0.08 * s, 0.02 * s, 0.4 * s]} castShadow>
                <boxGeometry args={[0.08 * s, 0.06 * s, 0.16 * s]} />
                <meshStandardMaterial color="#222" roughness={0.8} />
              </mesh>
            </>
          ) : (
            <>
              <mesh position={[side * 0.08 * s, 0.66 * s, 0]} castShadow>
                <capsuleGeometry args={[0.055 * s, 0.34 * s, 4, 8]} />
                <meshStandardMaterial color="#2a2a3a" roughness={0.7} />
              </mesh>
              <mesh position={[side * 0.08 * s, 0.28 * s, 0]} castShadow>
                <capsuleGeometry args={[0.045 * s, 0.32 * s, 4, 8]} />
                <meshStandardMaterial color="#2a2a3a" roughness={0.7} />
              </mesh>
              <mesh position={[side * 0.08 * s, 0.04 * s, 0.03 * s]} castShadow>
                <boxGeometry args={[0.08 * s, 0.06 * s, 0.16 * s]} />
                <meshStandardMaterial color="#222" roughness={0.8} />
              </mesh>
            </>
          )}
        </group>
      ))}
    </group>
  );
}
