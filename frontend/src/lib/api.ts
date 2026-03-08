const API_BASE = '/api';
const BACKEND_ORIGIN = process.env.NEXT_PUBLIC_BACKEND_ORIGIN || 'http://localhost:8000';
// Direct backend URL for large uploads (avoids Next.js proxy timeout)
const BACKEND_URL = `${BACKEND_ORIGIN}/api`;

async function parseApiError(res: Response, fallbackMessage: string): Promise<Error> {
  const fallback = `${fallbackMessage} (HTTP ${res.status})`;

  try {
    const body = await res.json();
    if (typeof body === 'string') return new Error(body || fallback);

    const detail = body?.detail;
    if (typeof detail === 'string') return new Error(detail || fallback);
    if (detail && typeof detail === 'object') {
      const code = detail.code ? `[${detail.code}] ` : '';
      const msg = detail.message || detail.error || JSON.stringify(detail);
      return new Error(`${code}${msg}`.trim() || fallback);
    }

    const top = body?.message || body?.error;
    if (typeof top === 'string' && top.trim()) return new Error(top.trim());

    return new Error(fallback);
  } catch {
    try {
      const text = await res.text();
      return new Error(text || fallback);
    } catch {
      return new Error(fallback);
    }
  }
}

export function resolveAssetUrl(path?: string | null): string | null {
  if (!path) return null;
  if (/^https?:\/\//i.test(path)) return path;
  if (!path.startsWith('/')) return `${BACKEND_ORIGIN}/${path}`;
  if (path.startsWith('/uploads/') || path.startsWith('/static/')) return `${BACKEND_ORIGIN}${path}`;
  return path;
}

export interface SessionStatus {
  status: 'processing' | 'complete' | 'error';
  stage: string;
  progress: number;
  message: string;
}

export interface GenerateResponse {
  session_id: string;
  status: string;
}

export interface SceneRoom {
  width: number;
  depth: number;
  height: number;
  floor_color: string;
  wall_color: string;
  ceiling_color: string;
}

export interface SceneLight {
  type: 'ambient' | 'point' | 'directional';
  color: string;
  intensity: number;
  position?: [number, number, number];
}

export type InteractionType = 'none' | 'sit' | 'write' | 'use' | 'open' | 'toggle';
export type ColliderType = 'none' | 'box' | 'sphere' | 'capsule' | 'mesh';

export interface InteractionAnchor {
  x: number;
  y: number;
  z: number;
}

export interface SceneObject {
  name: string;
  shape: 'box' | 'sphere' | 'cylinder' | 'plane';
  position: [number, number, number];
  size: [number, number, number];
  rotation?: [number, number, number];
  color: string;
  material?: string;
  roughness?: number;
  metalness?: number;
  interaction?: InteractionType;
  asset_ref?: string;
  asset_variant?: string;
  material_slots?: string[];
  collider_type?: ColliderType;
  nav_blocker?: boolean | null;
  interaction_anchor?: InteractionAnchor | null;
  animation_profile?: string;
  audio_profile?: string;
  lod_group?: string;
  spawn_tags?: string[];
  children?: SceneObject[];
}

export interface ScenePerson {
  name: string;
  position: [number, number, number];
  pose: 'standing' | 'sitting';
  facing: number;
  height: number;
  shirt_color: string;
  pants_color: string;
  skin_color: string;
}

export interface DoorReveal {
  object_name: string;
  room_type: string;
  floor_color: string;
  wall_color: string;
  visible_objects: { name: string; shape: string; color: string; size: [number, number, number]; offset: [number, number, number] }[];
}

export interface ContainerContents {
  object_name: string;
  items: { name: string; shape: string; color: string; size: [number, number, number]; offset: [number, number, number] }[];
}

export interface PersonDetails {
  person_name: string;
  hair_style: 'short' | 'long' | 'bald';
  hair_color: string;
  eye_color: string;
  facial_hair: 'none' | 'beard' | 'mustache' | 'goatee';
  shoe_color: string;
  gender_presentation: 'masculine' | 'feminine' | 'neutral';
}

export interface ObjectDetails {
  object_name: string;
  sub_type?: string;
  accent_color?: string;
  texture_hint?: string;
}

export interface SceneEnrichment {
  door_reveals: DoorReveal[];
  container_contents: ContainerContents[];
  person_details: PersonDetails[];
  object_details: ObjectDetails[];
}

export interface MissionObjective {
  id: string;
  description: string;
  targetName?: string;
  targetInteraction?: InteractionType | 'greet' | 'corner';
  completed: boolean;
}

export interface Mission {
  id: string;
  type: string;
  title: string;
  description: string;
  objectives: MissionObjective[];
  completed: boolean;
}

export interface SceneData {
  room: SceneRoom;
  lights: SceneLight[];
  objects: SceneObject[];
  people: ScenePerson[];
  enrichment?: SceneEnrichment;
}

export interface SceneBundleAssetRef {
  key: string;
  type: 'glb' | 'texture' | 'audio' | 'other';
  url: string;
  hash?: string;
  engine?: 'shared' | 'three' | 'godot' | 'unreal';
  placeholder?: boolean;
  asset_variant?: string;
  material_slots?: string[];
  lod_group?: string;
}

export interface SceneBundleData {
  session_id?: string;
  scene: SceneData;
  asset_manifest?: SceneBundleAssetRef[];
  dialogue_seeds?: string[];
}

export interface UnrealSceneBundleData {
  session_id: string;
  runtime: 'unreal';
  engine_version: string;
  map_name: string;
  streaming: {
    pixel_streaming: {
      signaling_url: string;
      player_url: string;
    };
  };
  scene: SceneData;
  asset_manifest: SceneBundleAssetRef[];
  spawn?: {
    default_player_start?: [number, number, number];
    spawn_tags?: string[];
  };
  world_settings?: {
    nanite?: boolean;
    lumen?: boolean;
    hardware_ray_tracing?: boolean;
    scalability?: string;
  };
  notes?: string[];
}

export async function generate3D(images: Record<string, File>): Promise<GenerateResponse> {
  const formData = new FormData();
  for (const [direction, file] of Object.entries(images)) {
    formData.append(`room_${direction}_image`, file);
  }
  // Post directly to backend to avoid Next.js proxy timeout on large uploads
  const res = await fetch(`${BACKEND_URL}/generate-3d`, { method: 'POST', body: formData });
  if (!res.ok) throw await parseApiError(res, 'Failed to generate 3D scene');
  return res.json();
}

export async function getStatus(sessionId: string): Promise<SessionStatus> {
  const res = await fetch(`${API_BASE}/status/${sessionId}`);
  if (!res.ok) throw await parseApiError(res, 'Failed to get status');
  return res.json();
}

export async function getLogs(sessionId: string): Promise<string[]> {
  const res = await fetch(`${API_BASE}/logs/${sessionId}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.logs || [];
}

function isFiniteNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function normalizeVec3(value: unknown, fallback: [number, number, number]): [number, number, number] {
  if (!Array.isArray(value) || value.length < 3) return fallback;
  const x = Number(value[0]);
  const y = Number(value[1]);
  const z = Number(value[2]);
  return [Number.isFinite(x) ? x : fallback[0], Number.isFinite(y) ? y : fallback[1], Number.isFinite(z) ? z : fallback[2]];
}

function normalizeColor(value: unknown, fallback: string): string {
  if (typeof value !== 'string') return fallback;
  const v = value.trim();
  if (!v) return fallback;
  return /^#[0-9a-fA-F]{3,8}$/.test(v) ? v : fallback;
}

function normalizeSceneObject(value: any, idx: number): SceneObject {
  const safeInteraction = ['none', 'sit', 'write', 'use', 'open', 'toggle'].includes(value?.interaction)
    ? value.interaction
    : 'none';

  const shape: SceneObject['shape'] = ['box', 'sphere', 'cylinder', 'plane'].includes(value?.shape)
    ? value.shape
    : 'box';

  const children = Array.isArray(value?.children)
    ? value.children.map((child: any, cIdx: number) => normalizeSceneObject(child, cIdx))
    : [];

  return {
    name: String(value?.name || `object_${idx}`),
    shape,
    position: normalizeVec3(value?.position, [0, 0, 0]),
    size: normalizeVec3(value?.size, [1, 1, 1]),
    rotation: Array.isArray(value?.rotation) ? normalizeVec3(value.rotation, [0, 0, 0]) : undefined,
    color: normalizeColor(value?.color, '#888888'),
    material: typeof value?.material === 'string' ? value.material : undefined,
    roughness: isFiniteNumber(value?.roughness) ? value.roughness : undefined,
    metalness: isFiniteNumber(value?.metalness) ? value.metalness : undefined,
    interaction: safeInteraction,
    asset_ref: typeof value?.asset_ref === 'string' ? value.asset_ref : undefined,
    asset_variant: typeof value?.asset_variant === 'string' ? value.asset_variant : undefined,
    material_slots: Array.isArray(value?.material_slots) ? value.material_slots.filter((slot: any) => typeof slot === 'string') : undefined,
    collider_type: typeof value?.collider_type === 'string' ? value.collider_type as ColliderType : undefined,
    nav_blocker: typeof value?.nav_blocker === 'boolean' ? value.nav_blocker : null,
    interaction_anchor: value?.interaction_anchor && typeof value.interaction_anchor === 'object'
      ? {
          x: Number(value.interaction_anchor.x) || 0,
          y: Number(value.interaction_anchor.y) || 0,
          z: Number(value.interaction_anchor.z) || 0,
        }
      : null,
    animation_profile: typeof value?.animation_profile === 'string' ? value.animation_profile : undefined,
    audio_profile: typeof value?.audio_profile === 'string' ? value.audio_profile : undefined,
    lod_group: typeof value?.lod_group === 'string' ? value.lod_group : undefined,
    spawn_tags: Array.isArray(value?.spawn_tags) ? value.spawn_tags.filter((tag: any) => typeof tag === 'string') : undefined,
    children,
  };
}

function normalizeScenePerson(value: any, idx: number): ScenePerson {
  const pose: ScenePerson['pose'] = value?.pose === 'sitting'
    ? 'sitting'
    : typeof value?.animation === 'string' && /sit/i.test(value.animation)
      ? 'sitting'
      : 'standing';

  const facing = isFiniteNumber(value?.facing)
    ? value.facing
    : Array.isArray(value?.rotation)
      ? Number(value.rotation[1] ?? value.rotation[2] ?? 0)
      : 0;

  return {
    name: String(value?.name || `person_${idx}`),
    position: normalizeVec3(value?.position, [0, 0, 0]),
    pose,
    facing: Number.isFinite(facing) ? facing : 0,
    height: isFiniteNumber(value?.height) && value.height > 0 ? value.height : 1.72,
    shirt_color: normalizeColor(value?.shirt_color, '#5577aa'),
    pants_color: normalizeColor(value?.pants_color, '#2a2a3a'),
    skin_color: normalizeColor(value?.skin_color, '#d7a07b'),
  };
}

function normalizeSceneData(raw: any): SceneData {
  const roomRaw = raw?.room || {};
  const room: SceneRoom = {
    width: isFiniteNumber(roomRaw.width) && roomRaw.width > 1 ? roomRaw.width : 8,
    depth: isFiniteNumber(roomRaw.depth) && roomRaw.depth > 1 ? roomRaw.depth : 6,
    height: isFiniteNumber(roomRaw.height) && roomRaw.height > 1 ? roomRaw.height : 2.8,
    floor_color: normalizeColor(roomRaw.floor_color, '#6b5c4a'),
    wall_color: normalizeColor(roomRaw.wall_color, '#d9d3c6'),
    ceiling_color: normalizeColor(roomRaw.ceiling_color, '#f0f0f0'),
  };

  const lights: SceneLight[] = Array.isArray(raw?.lights)
    ? raw.lights
        .map((light: any) => ({
          type: ['ambient', 'point', 'directional'].includes(light?.type) ? light.type : 'ambient',
          color: normalizeColor(light?.color, '#ffffff'),
          intensity: isFiniteNumber(light?.intensity) ? light.intensity : 0.5,
          position: Array.isArray(light?.position) ? normalizeVec3(light.position, [0, room.height - 0.2, 0]) : undefined,
        }))
        .slice(0, 24)
    : [];

  const objects: SceneObject[] = Array.isArray(raw?.objects)
    ? raw.objects.map((obj: any, idx: number) => normalizeSceneObject(obj, idx))
    : [];

  const people: ScenePerson[] = Array.isArray(raw?.people)
    ? raw.people.map((person: any, idx: number) => normalizeScenePerson(person, idx))
    : [];

  return {
    room,
    lights,
    objects,
    people,
    enrichment: raw?.enrichment && typeof raw.enrichment === 'object'
      ? {
          door_reveals: Array.isArray(raw.enrichment.door_reveals) ? raw.enrichment.door_reveals : [],
          container_contents: Array.isArray(raw.enrichment.container_contents) ? raw.enrichment.container_contents : [],
          person_details: Array.isArray(raw.enrichment.person_details) ? raw.enrichment.person_details : [],
          object_details: Array.isArray(raw.enrichment.object_details) ? raw.enrichment.object_details : [],
        }
      : undefined,
  };
}

export async function getSceneData(sessionId: string): Promise<SceneData> {
  const timeoutMs = Number(process.env.NEXT_PUBLIC_SCENE_FETCH_TIMEOUT_MS || 12000);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const res = await fetch(`${API_BASE}/universe/${sessionId}/scene.json`, {
      signal: controller.signal,
      cache: 'no-store',
    });
    if (!res.ok) throw await parseApiError(res, 'Scene not found');
    const raw = await res.json();
    return normalizeSceneData(raw);
  } catch (error: any) {
    if (error?.name === 'AbortError') {
      throw new Error(`Scene request timed out after ${timeoutMs}ms. Check backend or port-forward stability.`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export async function getSceneBundle(sessionId: string): Promise<SceneBundleData> {
  const res = await fetch(`${API_BASE}/universe/${sessionId}/bundle`);
  if (!res.ok) throw await parseApiError(res, 'Scene bundle not found');
  return res.json();
}

export async function getUnrealSceneBundle(sessionId: string): Promise<UnrealSceneBundleData> {
  const res = await fetch(`${API_BASE}/universe/${sessionId}/unreal/scene-bundle`);
  if (!res.ok) throw await parseApiError(res, 'Unreal scene bundle not found');
  return res.json();
}

export function getCubemapUrl(sessionId: string, direction: string): string {
  return `${API_BASE}/universe/${sessionId}/cubemap/${direction}`;
}

export interface VideoSegmentationSessionStatus {
  session_id: string;
  status: 'processing' | 'live_capturing' | 'ready_for_selection' | 'generating_scene' | 'complete' | 'error';
  stage: string;
  progress: number;
  message: string;
  frame_interval_sec: number;
  frames_total: number;
  frames_segmented: number;
  selected_frame_ids: string[];
  overshoot_mode?: 'mock' | 'live';
  overshoot_adapter?: string;
  gemini_model?: string;
  scene_id?: string;
  error?: string;
  realtime?: boolean;
  capture_mode?: 'interval' | 'scene_change';
  event_seq?: number;
}

export interface SegmentedObject {
  id: string;
  label: string;
  confidence: number;
  bbox: number[];
  polygon: number[][];
  mask?: { path?: string | null };
  metadata?: Record<string, any>;
}

export interface SegmentedFrame {
  frame_id: string;
  frame_index: number;
  timestamp_sec: number;
  frame_path: string;
  frame_url: string;
  overlay_url?: string;
  objects: SegmentedObject[];
  status: 'pending' | 'complete' | 'error';
  error?: string;
}

export interface VideoSegmentationResult {
  session_id: string;
  scene_id: string;
  created_at: string;
  selected_frame_ids: string[];
  selected_frames: SegmentedFrame[];
  models?: {
    gemini?: string;
    overshoot_adapter?: string;
    overshoot_mode?: 'mock' | 'live';
  };
  play_routes?: {
    three_url: string;
    unreal_url?: string;
    unreal_player_url?: string;
    unreal_stream_available?: boolean;
  };
  bundle: UnrealSceneBundleData & {
    missions?: any[];
    mission_objects?: any[];
    segmentation_summary?: Record<string, any>;
  };
}

export async function createVideoSegmentationSession(video: File, frameIntervalSec = 10): Promise<{ session_id: string }> {
  const formData = new FormData();
  formData.append('video', video);
  formData.append('frame_interval_sec', String(frameIntervalSec));

  const res = await fetch(`${BACKEND_URL}/video-segmentation/sessions`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw await parseApiError(res, 'Failed to create video segmentation session');
  return res.json();
}

export async function getVideoSegmentationSession(sessionId: string): Promise<VideoSegmentationSessionStatus> {
  const res = await fetch(`${API_BASE}/video-segmentation/sessions/${sessionId}`);
  if (!res.ok) throw await parseApiError(res, 'Failed to fetch video segmentation session');
  return res.json();
}

export async function getVideoSegmentationFrames(sessionId: string): Promise<{ frames: SegmentedFrame[] }> {
  const res = await fetch(`${API_BASE}/video-segmentation/sessions/${sessionId}/frames`);
  if (!res.ok) throw await parseApiError(res, 'Failed to fetch segmented frames');
  return res.json();
}

export interface SessionEvent {
  seq: number;
  ts: string;
  type: string;
  message: string;
  payload?: Record<string, any>;
}

export async function createRealtimeSegmentationSession(
  frameIntervalSec = 10,
  captureMode: 'interval' | 'scene_change' = 'interval'
): Promise<VideoSegmentationSessionStatus> {
  const formData = new FormData();
  formData.append('frame_interval_sec', String(frameIntervalSec));
  formData.append('capture_mode', captureMode);

  const res = await fetch(`${BACKEND_URL}/video-segmentation/realtime/sessions`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw await parseApiError(res, 'Failed to create realtime session');
  return res.json();
}

export async function uploadRealtimeFrame(
  sessionId: string,
  frameBlob: Blob,
  timestampSec?: number
): Promise<{ accepted: boolean; frame: SegmentedFrame }> {
  const formData = new FormData();
  formData.append('frame', frameBlob, `frame_${Date.now()}.jpg`);
  if (typeof timestampSec === 'number') formData.append('timestamp_sec', String(timestampSec));

  const res = await fetch(`${BACKEND_URL}/video-segmentation/realtime/sessions/${sessionId}/frames`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) throw await parseApiError(res, 'Failed to upload realtime frame');
  return res.json();
}

export async function stopRealtimeSegmentationSession(sessionId: string): Promise<VideoSegmentationSessionStatus> {
  const res = await fetch(`${BACKEND_URL}/video-segmentation/realtime/sessions/${sessionId}/stop`, { method: 'POST' });
  if (!res.ok) throw await parseApiError(res, 'Failed to stop realtime session');
  return res.json();
}

export async function getVideoSegmentationEvents(
  sessionId: string,
  since = 0
): Promise<{ latest: number; events: SessionEvent[] }> {
  const res = await fetch(`${API_BASE}/video-segmentation/sessions/${sessionId}/events?since=${since}`);
  if (!res.ok) throw await parseApiError(res, 'Failed to fetch session events');
  return res.json();
}

export async function submitSelectedFrames(sessionId: string, selectedFrameIds: string[]): Promise<{ scene_id: string; result: VideoSegmentationResult }> {
  const res = await fetch(`${API_BASE}/video-segmentation/sessions/${sessionId}/scene`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ selected_frame_ids: selectedFrameIds }),
  });
  if (!res.ok) throw await parseApiError(res, 'Failed to generate scene from selected frames');
  return res.json();
}

export async function getVideoSegmentationResult(sessionId: string): Promise<VideoSegmentationResult> {
  const res = await fetch(`${API_BASE}/video-segmentation/sessions/${sessionId}/result`);
  if (!res.ok) throw await parseApiError(res, 'Failed to fetch scene result');
  return res.json();
}
