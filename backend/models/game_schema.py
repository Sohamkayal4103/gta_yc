from pydantic import BaseModel, Field
from typing import List, Optional, Literal


ColliderType = Literal["none", "box", "sphere", "capsule", "mesh"]


class RuntimeObjectMetadata(BaseModel):
    """Canonical runtime metadata shared by Godot/Three/Unreal consumers."""

    asset_ref: Optional[str] = None
    asset_variant: Optional[str] = None
    material_slots: List[str] = Field(default_factory=list)
    collider_type: ColliderType = "box"
    nav_blocker: Optional[bool] = None
    interaction_anchor: Optional[dict] = None
    animation_profile: Optional[str] = None
    audio_profile: Optional[str] = None
    lod_group: Optional[str] = None
    spawn_tags: List[str] = Field(default_factory=list)


class RoomObject(RuntimeObjectMetadata):
    name: str
    object_type: str  # furniture, electronics, decoration, storage, appliance
    x_percent: float  # 0.0–1.0 position from left
    y_percent: float  # 0.0–1.0 position from top
    width_percent: float
    height_percent: float
    is_interactable: bool
    description: str
    game_name: Optional[str] = None  # Genre-transformed name (e.g. "bookshelf" → "data terminal")


class WallSegment(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class RoomLayout(BaseModel):
    room_width_meters: float
    room_height_meters: float
    objects: List[RoomObject]
    walls: List[WallSegment]
    door_positions: List[dict]
    room_description: str
    lighting: str
    floor_type: str


class MissionStep(BaseModel):
    instruction: str
    target_object: Optional[str] = None
    action: str  # go_to, interact, collect, talk_to
    dialogue: Optional[str] = None


class Mission(BaseModel):
    id: str
    title: str
    description: str
    genre_flavor: str
    steps: List[MissionStep]
    reward_text: str
    npc_name: Optional[str] = None


class MissionPack(BaseModel):
    missions: List[Mission]
    npcs: List[dict]


class GameAssets(BaseModel):
    map: str = "map.png"
    player: str = "player.png"
    npcs: List[str] = Field(default_factory=list)
    items: List[str] = Field(default_factory=list)


class GameAudio(BaseModel):
    soundtrack: str = "bgm.mp3"
    sfx: dict = Field(default_factory=dict)


class CollisionRect(BaseModel):
    x: float
    y: float
    w: float
    h: float
    object_name: Optional[str] = None
    collider_type: ColliderType = "box"
    nav_blocker: Optional[bool] = None


class Interactable(RuntimeObjectMetadata):
    id: str
    name: str
    game_name: str
    x: float
    y: float
    w: float
    h: float
    description: str


class SpawnPoint(BaseModel):
    x: float
    y: float


class GameManifest(BaseModel):
    session_id: str
    genre: str
    room_layout: RoomLayout
    missions: MissionPack
    assets: GameAssets
    audio: GameAudio
    map_width: int
    map_height: int
    collision_rects: List[CollisionRect]
    spawn_point: SpawnPoint
    interactables: List[Interactable]
