from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class SegmentMask(BaseModel):
    path: str | None = None
    width: int | None = None
    height: int | None = None


class SegmentObject(BaseModel):
    id: str
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    bbox: list[float] = Field(default_factory=list, description="[x, y, w, h] in pixels")
    polygon: list[list[float]] = Field(default_factory=list)
    mask: SegmentMask | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FrameSegmentation(BaseModel):
    frame_id: str
    frame_index: int
    timestamp_sec: float
    frame_path: str
    overlay_path: str | None = None
    objects: list[SegmentObject] = Field(default_factory=list)
    status: Literal["pending", "complete", "error"] = "pending"
    error: str | None = None


class VideoSessionState(BaseModel):
    session_id: str
    status: Literal["processing", "live_capturing", "ready_for_selection", "generating_scene", "complete", "error"]
    stage: str
    progress: int = Field(ge=0, le=100)
    message: str
    frame_interval_sec: float = Field(gt=0)
    frames_total: int = 0
    frames_segmented: int = 0
    selected_frame_ids: list[str] = Field(default_factory=list)
    scene_id: str | None = None
    error: str | None = None

    # Runtime metadata for UX transparency
    overshoot_mode: Literal["mock", "live"] = "mock"
    overshoot_adapter: str = "generic_v1"
    gemini_model: str = "gemini-2.5-pro"

    # Realtime capture metadata (used by browser camera sessions)
    realtime: bool = False
    capture_mode: Literal["interval", "scene_change"] = "interval"
    event_seq: int = 0


class MissionObjective(BaseModel):
    id: str
    type: Literal["investigate", "interact", "collect", "rescue", "secure", "navigate"]
    description: str
    target_label: str | None = None
    confidence: float | None = None


class MissionSpec(BaseModel):
    id: str
    title: str
    description: str
    difficulty: Literal["easy", "medium", "hard"] = "easy"
    objectives: list[MissionObjective] = Field(default_factory=list)
    rewards: dict[str, Any] = Field(default_factory=dict)


class UnrealSceneBundle(BaseModel):
    session_id: str
    scene_id: str
    runtime: Literal["unreal"] = "unreal"
    engine_version: str = "5.x"
    map_name: str
    world_settings: dict[str, Any] = Field(default_factory=dict)
    scene: dict[str, Any] = Field(default_factory=dict)
    missions: list[MissionSpec] = Field(default_factory=list)
    mission_objects: list[dict[str, Any]] = Field(default_factory=list)
    segmentation_summary: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
