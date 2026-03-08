'use client';

import { useEffect, useState, useCallback, useMemo } from 'react';
import * as THREE from 'three';
import { SceneData, getSceneData, DoorReveal, ContainerContents, PersonDetails, ObjectDetails, Mission } from '@/lib/api';
import { InteractionPrompt, ActiveInteraction, MissionEvent } from './ThirdPersonController';
import { generateMissions } from '@/lib/MissionSystem';
import CubemapSkybox from './CubemapSkybox';
import PBRObject from './PBRObject';
import HumanFigure from './HumanFigure';
import ThirdPersonController from './ThirdPersonController';

interface SceneBuilderProps {
  sessionId: string;
  onCommentary?: (lines: string[]) => void;
  onInteractionPrompt?: (prompt: InteractionPrompt | null) => void;
  onActiveInteraction?: (interaction: ActiveInteraction | null) => void;
  onMissionsUpdate?: (missions: Mission[]) => void;
  onMissionCompleted?: (mission: Mission) => void;
  onSceneLoadState?: (state: { loading: boolean; error: string | null; ready: boolean }) => void;
}

export default function SceneBuilder({ sessionId, onCommentary, onInteractionPrompt, onActiveInteraction, onMissionsUpdate, onMissionCompleted, onSceneLoadState }: SceneBuilderProps) {
  const [scene, setScene] = useState<SceneData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeInteraction, setActiveInteraction] = useState<ActiveInteraction | null>(null);
  const [playerPosition, setPlayerPosition] = useState<[number, number, number]>([0, 0, 0]);
  const [missions, setMissions] = useState<Mission[]>([]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setScene(null);

    getSceneData(sessionId)
      .then((data) => {
        if (cancelled) return;
        setScene(data);
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e?.message || 'Failed to load scene');
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId]);

  useEffect(() => {
    onSceneLoadState?.({ loading, error, ready: !!scene && !loading && !error });
  }, [loading, error, scene, onSceneLoadState]);

  // Generate missions once scene loads
  useEffect(() => {
    if (scene) {
      const m = generateMissions(scene.objects, scene.people);
      setMissions(m);
      onMissionsUpdate?.(m);
      return;
    }
    setMissions([]);
    onMissionsUpdate?.([]);
  }, [scene, onMissionsUpdate]);

  const handleMissionEvent = useCallback((event: MissionEvent) => {
    setMissions(prev => {
      const updated = prev.map(mission => {
        if (mission.completed) return mission;
        const updatedObjectives = mission.objectives.map(obj => {
          if (obj.completed) return obj;
          if (obj.targetInteraction === event.type && obj.targetName === event.targetName) {
            return { ...obj, completed: true };
          }
          return obj;
        });
        const allDone = updatedObjectives.every(o => o.completed);
        const wasComplete = mission.completed;
        const newMission = { ...mission, objectives: updatedObjectives, completed: allDone };
        if (allDone && !wasComplete) {
          onMissionCompleted?.(newMission);
        }
        return newMission;
      });
      onMissionsUpdate?.(updated);
      return updated;
    });
  }, [onMissionsUpdate, onMissionCompleted]);

  const handleActiveInteraction = useCallback((interaction: ActiveInteraction | null) => {
    setActiveInteraction(interaction);
    onActiveInteraction?.(interaction);
  }, [onActiveInteraction]);

  const handlePlayerPosition = useCallback((pos: [number, number, number]) => {
    setPlayerPosition(pos);
  }, []);

  // Build lookup maps for enrichment data
  const doorRevealMap = useMemo(() => {
    const map = new Map<string, DoorReveal>();
    if (scene?.enrichment?.door_reveals) {
      for (const dr of scene.enrichment.door_reveals) {
        map.set(dr.object_name, dr);
      }
    }
    return map;
  }, [scene?.enrichment?.door_reveals]);

  const containerContentsMap = useMemo(() => {
    const map = new Map<string, ContainerContents>();
    if (scene?.enrichment?.container_contents) {
      for (const cc of scene.enrichment.container_contents) {
        map.set(cc.object_name, cc);
      }
    }
    return map;
  }, [scene?.enrichment?.container_contents]);

  const personDetailsMap = useMemo(() => {
    const map = new Map<string, PersonDetails>();
    if (scene?.enrichment?.person_details) {
      for (const pd of scene.enrichment.person_details) {
        map.set(pd.person_name, pd);
      }
    }
    return map;
  }, [scene?.enrichment?.person_details]);

  const objectDetailsMap = useMemo(() => {
    const map = new Map<string, ObjectDetails>();
    if (scene?.enrichment?.object_details) {
      for (const od of scene.enrichment.object_details) {
        map.set(od.object_name, od);
      }
    }
    return map;
  }, [scene?.enrichment?.object_details]);

  // Track which doors are open for collision system
  const openDoors = useMemo(() => {
    const set = new Set<string>();
    if (activeInteraction?.type === 'open') {
      const doorName = String(activeInteraction.objectName ?? '').trim();
      if (doorName) set.add(doorName);
    }
    return set;
  }, [activeInteraction]);

  if (loading) return null;
  if (error) return null;
  if (!scene) return null;

  const { room } = scene;
  const halfW = room.width / 2;
  const halfD = room.depth / 2;

  return (
    <>
      <CubemapSkybox sessionId={sessionId} />

      {/* Lights */}
      {scene.lights.map((light, i) => {
        if (light.type === 'ambient') {
          return <ambientLight key={i} color={light.color} intensity={light.intensity} />;
        }
        if (light.type === 'point' && light.position) {
          return (
            <pointLight
              key={i}
              color={light.color}
              intensity={light.intensity}
              position={light.position}
              castShadow
              shadow-mapSize-width={1024}
              shadow-mapSize-height={1024}
            />
          );
        }
        if (light.type === 'directional' && light.position) {
          return (
            <directionalLight
              key={i}
              color={light.color}
              intensity={light.intensity}
              position={light.position}
              castShadow
              shadow-mapSize-width={2048}
              shadow-mapSize-height={2048}
            />
          );
        }
        return null;
      })}

      {/* Hemisphere light for warm ambient fill */}
      <hemisphereLight args={['#ffeedd', '#334455', 0.3]} />

      {/* Floor */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0, 0]} receiveShadow>
        <planeGeometry args={[room.width, room.depth]} />
        <meshStandardMaterial color={room.floor_color} roughness={0.8} side={THREE.DoubleSide} />
      </mesh>

      {/* Floor inset border (lighter, slightly raised) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.001, 0]} receiveShadow>
        <planeGeometry args={[room.width - 0.3, room.depth - 0.3]} />
        <meshStandardMaterial
          color={new THREE.Color(room.floor_color).offsetHSL(0, -0.05, 0.06)}
          roughness={0.75}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* Ceiling */}
      <mesh rotation={[Math.PI / 2, 0, 0]} position={[0, room.height, 0]} receiveShadow>
        <planeGeometry args={[room.width, room.depth]} />
        <meshStandardMaterial color={room.ceiling_color} roughness={0.9} side={THREE.DoubleSide} />
      </mesh>

      {/* Walls with slight color variation per wall */}
      {/* Front wall (-Z) — base color */}
      <mesh position={[0, room.height / 2, -halfD]} receiveShadow>
        <planeGeometry args={[room.width, room.height]} />
        <meshStandardMaterial color={room.wall_color} roughness={0.7} side={THREE.DoubleSide} />
      </mesh>
      {/* Back wall (+Z) — slightly darker */}
      <mesh position={[0, room.height / 2, halfD]} rotation={[0, Math.PI, 0]} receiveShadow>
        <planeGeometry args={[room.width, room.height]} />
        <meshStandardMaterial
          color={new THREE.Color(room.wall_color).offsetHSL(0, 0, -0.03)}
          roughness={0.7}
          side={THREE.DoubleSide}
        />
      </mesh>
      {/* Left wall (-X) — slightly darker */}
      <mesh position={[-halfW, room.height / 2, 0]} rotation={[0, Math.PI / 2, 0]} receiveShadow>
        <planeGeometry args={[room.depth, room.height]} />
        <meshStandardMaterial
          color={new THREE.Color(room.wall_color).offsetHSL(0, 0, -0.015)}
          roughness={0.7}
          side={THREE.DoubleSide}
        />
      </mesh>
      {/* Right wall (+X) — slightly darker */}
      <mesh position={[halfW, room.height / 2, 0]} rotation={[0, -Math.PI / 2, 0]} receiveShadow>
        <planeGeometry args={[room.depth, room.height]} />
        <meshStandardMaterial
          color={new THREE.Color(room.wall_color).offsetHSL(0, 0, -0.02)}
          roughness={0.7}
          side={THREE.DoubleSide}
        />
      </mesh>

      {/* === Baseboards (8cm tall, 2cm deep, off-white) === */}
      {/* Front baseboard */}
      <mesh position={[0, 0.04, -halfD + 0.01]}>
        <boxGeometry args={[room.width, 0.08, 0.02]} />
        <meshStandardMaterial color="#e8e4de" roughness={0.6} />
      </mesh>
      {/* Back baseboard */}
      <mesh position={[0, 0.04, halfD - 0.01]}>
        <boxGeometry args={[room.width, 0.08, 0.02]} />
        <meshStandardMaterial color="#e8e4de" roughness={0.6} />
      </mesh>
      {/* Left baseboard */}
      <mesh position={[-halfW + 0.01, 0.04, 0]}>
        <boxGeometry args={[0.02, 0.08, room.depth]} />
        <meshStandardMaterial color="#e8e4de" roughness={0.6} />
      </mesh>
      {/* Right baseboard */}
      <mesh position={[halfW - 0.01, 0.04, 0]}>
        <boxGeometry args={[0.02, 0.08, room.depth]} />
        <meshStandardMaterial color="#e8e4de" roughness={0.6} />
      </mesh>

      {/* === Crown molding (5cm tall, 1.5cm deep) === */}
      {/* Front crown */}
      <mesh position={[0, room.height - 0.025, -halfD + 0.0075]}>
        <boxGeometry args={[room.width, 0.05, 0.015]} />
        <meshStandardMaterial color="#f0ece6" roughness={0.5} />
      </mesh>
      {/* Back crown */}
      <mesh position={[0, room.height - 0.025, halfD - 0.0075]}>
        <boxGeometry args={[room.width, 0.05, 0.015]} />
        <meshStandardMaterial color="#f0ece6" roughness={0.5} />
      </mesh>
      {/* Left crown */}
      <mesh position={[-halfW + 0.0075, room.height - 0.025, 0]}>
        <boxGeometry args={[0.015, 0.05, room.depth]} />
        <meshStandardMaterial color="#f0ece6" roughness={0.5} />
      </mesh>
      {/* Right crown */}
      <mesh position={[halfW - 0.0075, room.height - 0.025, 0]}>
        <boxGeometry args={[0.015, 0.05, room.depth]} />
        <meshStandardMaterial color="#f0ece6" roughness={0.5} />
      </mesh>

      {/* Objects with enrichment data */}
      {scene.objects.map((obj, i) => (
        <PBRObject
          key={`obj-${i}`}
          obj={obj}
          activeInteraction={activeInteraction}
          doorReveal={doorRevealMap.get(obj.name)}
          containerContents={containerContentsMap.get(obj.name)}
          objectDetails={objectDetailsMap.get(obj.name)}
        />
      ))}

      {/* People with enrichment details */}
      {scene.people.map((person, i) => (
        <HumanFigure
          key={`person-${i}`}
          person={person}
          isBeingGreeted={activeInteraction?.personName === person.name}
          details={personDetailsMap.get(person.name)}
          playerPosition={playerPosition}
        />
      ))}

      <ThirdPersonController
        roomBounds={{ halfW, halfD, height: room.height }}
        objects={scene.objects}
        people={scene.people}
        onCommentary={onCommentary}
        onInteractionPrompt={onInteractionPrompt}
        onActiveInteraction={handleActiveInteraction}
        onPlayerPosition={handlePlayerPosition}
        onMissionEvent={handleMissionEvent}
        openDoors={openDoors}
      />
    </>
  );
}
