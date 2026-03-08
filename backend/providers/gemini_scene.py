from __future__ import annotations

import json
import mimetypes
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from backend.config import GEMINI_API_KEY, GEMINI_MODEL


SCENE_PROMPT = """You are an Unreal Engine technical level designer and gameplay space planner.
Given selected raw video frames, perform your own semantic segmentation/reasoning internally and generate a realistic indoor scene JSON.

Scene context:
{scene_context}

Hard requirements:
- Output valid JSON only.
- Include keys: room, lights, objects, people.
- room: width/depth/height in meters. Keep room large and playable (target >= 10m width and >= 9m depth unless context strongly forbids it).
- Keep a wide, clear navigable center lane for player movement and mission traversal.
- lights: include at least one ambient and one key/directional light.
- objects: include plausible materials for ray tracing (material, roughness, metalness).
- Replicate detected object families by your visual analysis so the room is coherent and not sparse.
- Add realistic decorative details (plants, wall decor, clutter, cables, rugs, books) consistent with style cues.
- people: include person entries only when people are visually present, and match multi-person counts when multiple people are visible.
- MANDATORY: include one object named exactly "Hidden Mac Mini" placed in a plausible hidden location.
- Mission design intent: user must search and find Hidden Mac Mini; mission completes on discovery.
- Objects should include runtime metadata fields:
  asset_ref, asset_variant, material_slots, collider_type, nav_blocker, interaction_anchor,
  animation_profile, audio_profile, lod_group, spawn_tags.

Layout policy (critical):
- DO NOT trust raw Overshoot bbox/polygon coordinates for exact placement.
- Use object type/name frequencies and semantic co-occurrence first.
- Place major furniture on walls/perimeter, keep middle mostly open, and place doors where room transitions make sense.
- If layout implies multiple rooms/areas, include at least one visible connecting door object between areas.

JSON schema:
{{
  "room": {{"width": 10.2, "depth": 9.4, "height": 3.1, "floor_color": "#777777", "wall_color": "#cccccc", "ceiling_color": "#f2f2f2"}},
  "lights": [{{"type": "ambient", "color": "#ffffff", "intensity": 0.45}}],
  "objects": [{{
    "name": "Desk",
    "shape": "box",
    "position": [0,0.4,0],
    "size": [1.2,0.8,0.6],
    "rotation": [0,0,0],
    "color": "#8b5a2b",
    "material": "wood",
    "roughness": 0.7,
    "metalness": 0.1,
    "interaction": "use",
    "asset_ref": "/Game/RealmCast/Generated/desk",
    "asset_variant": "default",
    "material_slots": ["base"],
    "collider_type": "box",
    "nav_blocker": true,
    "interaction_anchor": {{"x": 0, "y": 0.8, "z": 0.4}},
    "animation_profile": null,
    "audio_profile": "roomtone",
    "lod_group": "furniture",
    "spawn_tags": ["generated"],
    "children": []
  }}],
  "people": []
}}
"""


class GeminiSceneClient:
    def __init__(self) -> None:
        self.enabled = bool(GEMINI_API_KEY)
        self.client = genai.Client(api_key=GEMINI_API_KEY) if self.enabled else None
        self.model = GEMINI_MODEL

    def _collect_label_stats(self, selected_frames: list[dict[str, Any]]) -> tuple[Counter[str], dict[str, float]]:
        label_counts: Counter[str] = Counter()
        confidences: dict[str, list[float]] = defaultdict(list)
        for frame in selected_frames:
            for obj in frame.get("objects", []):
                label = str(obj.get("label", "unknown")).strip().lower()
                if not label:
                    continue
                label_counts[label] += 1
                confidences[label].append(float(obj.get("confidence", 0.0) or 0.0))

        avg_conf = {
            label: (sum(vals) / len(vals)) if vals else 0.0
            for label, vals in confidences.items()
        }
        return label_counts, avg_conf

    def _infer_style_cues(self, label_counts: Counter[str]) -> list[str]:
        labels = set(label_counts.keys())
        cues: list[str] = []

        office_hits = {"desk", "monitor", "laptop", "keyboard", "mouse", "whiteboard", "printer"}
        kitchen_hits = {"fridge", "microwave", "sink", "cabinet", "stove", "oven", "kettle"}
        living_hits = {"sofa", "tv", "lamp", "coffee table", "bookshelf", "rug"}
        bedroom_hits = {"bed", "wardrobe", "nightstand", "dresser", "pillow"}

        if labels & office_hits:
            cues.append("office / workroom")
        if labels & kitchen_hits:
            cues.append("kitchen / pantry")
        if labels & living_hits:
            cues.append("living room")
        if labels & bedroom_hits:
            cues.append("bedroom")
        if not cues:
            cues.append("multi-purpose modern indoor room")

        if any("wood" in l for l in labels):
            cues.append("warm wood accents")
        if any("metal" in l for l in labels):
            cues.append("metallic modern details")

        return cues

    def _geometry_reliability(self, selected_frames: list[dict[str, Any]]) -> dict[str, Any]:
        total = 0
        bbox_valid = 0
        polygon_valid = 0

        for frame in selected_frames:
            for obj in frame.get("objects", []):
                total += 1
                bbox = obj.get("bbox") or []
                if isinstance(bbox, list) and len(bbox) == 4:
                    w = float(bbox[2] or 0)
                    h = float(bbox[3] or 0)
                    if w > 0 and h > 0:
                        bbox_valid += 1

                poly = obj.get("polygon") or []
                if isinstance(poly, list) and len(poly) >= 3:
                    polygon_valid += 1

        if total == 0:
            return {"quality": "low", "score": 0.0, "bbox_valid_ratio": 0.0, "polygon_valid_ratio": 0.0}

        bbox_ratio = bbox_valid / total
        poly_ratio = polygon_valid / total
        score = (bbox_ratio * 0.55) + (poly_ratio * 0.45)

        if score >= 0.75:
            quality = "high"
        elif score >= 0.45:
            quality = "medium"
        else:
            quality = "low"

        return {
            "quality": quality,
            "score": round(score, 3),
            "bbox_valid_ratio": round(bbox_ratio, 3),
            "polygon_valid_ratio": round(poly_ratio, 3),
        }

    def _suggest_object_families(self, label_counts: Counter[str]) -> list[str]:
        families: list[str] = []
        top_labels = [label for label, _ in label_counts.most_common(8)]

        if any(k in l for l in top_labels for k in ["chair", "stool"]):
            families.append("chairs")
        if any(k in l for l in top_labels for k in ["table", "desk"]):
            families.append("tables/desks")
        if any(k in l for l in top_labels for k in ["lamp", "light"]):
            families.append("lamps")
        if any(k in l for l in top_labels for k in ["shelf", "cabinet", "drawer"]):
            families.append("storage units")
        if not families:
            families.extend(["decor props", "small furniture", "storage units"])

        return families

    def _build_scene_context(self, selected_frames: list[dict[str, Any]]) -> str:
        frame_lines: list[str] = []
        for frame in selected_frames:
            frame_lines.append(
                f"- frame_id={frame.get('frame_id')} t={frame.get('timestamp_sec')}s path={frame.get('frame_path')}"
            )

        return "\n".join(
            [
                "Attached inputs are RAW selected frames from user capture.",
                "No Overshoot geometry (bbox/polygon/mask/coordinates) is provided here.",
                "Infer semantics directly from pixels across all attached frames before composing layout.",
                "",
                "Frame references:",
                *(frame_lines or ["- none"]),
                "",
                "Mission objective (must preserve): find hidden Mac mini, mission complete on discovery.",
            ]
        )

    def _interaction_for_label(self, label: str) -> str:
        lx = label.lower()
        if any(k in lx for k in ["chair", "sofa", "bench", "stool", "seat"]):
            return "sit"
        if any(k in lx for k in ["monitor", "laptop", "computer", "desk", "keyboard", "tv"]):
            return "use"
        if any(k in lx for k in ["door", "cabinet", "drawer", "shelf", "closet", "fridge"]):
            return "open"
        if any(k in lx for k in ["lamp", "switch", "fan", "light"]):
            return "toggle"
        return "none"

    def _size_for_label(self, label: str) -> list[float]:
        lx = label.lower()
        if any(k in lx for k in ["desk", "table"]):
            return [1.4, 0.82, 0.8]
        if any(k in lx for k in ["chair", "stool", "seat"]):
            return [0.62, 0.95, 0.62]
        if "sofa" in lx or "couch" in lx:
            return [1.9, 0.9, 0.9]
        if any(k in lx for k in ["shelf", "cabinet", "wardrobe", "bookshelf", "closet"]):
            return [1.0, 1.9, 0.45]
        if any(k in lx for k in ["door", "doorway"]):
            return [1.0, 2.1, 0.12]
        if any(k in lx for k in ["plant", "lamp"]):
            return [0.45, 1.35, 0.45]
        if any(k in lx for k in ["rug", "carpet"]):
            return [2.8, 0.02, 2.1]
        return [0.75, 0.95, 0.6]

    def _estimated_person_count(self, label_counts: Counter[str]) -> int:
        person_count = 0
        for label, count in label_counts.items():
            if "person" in label.lower() or "human" in label.lower():
                person_count += count
        if person_count <= 0:
            return 0
        if person_count >= 8:
            return 3
        if person_count >= 4:
            return 2
        return 1

    def _needs_connection_door(self, label_counts: Counter[str]) -> bool:
        lower = [k.lower() for k in label_counts.keys()]
        explicit_multizone = any(
            token in label
            for label in lower
            for token in ["hall", "corridor", "kitchen", "bedroom", "bathroom", "lobby", "room 2", "second room"]
        )
        detected_doors = sum(v for k, v in label_counts.items() if "door" in k.lower())
        return explicit_multizone or detected_doors >= 2

    def _make_object(self, name: str, label: str, pos_x: float, pos_y: float, pos_z: float, idx: int) -> dict[str, Any]:
        slug = label.replace(" ", "_").lower()
        return {
            "name": name,
            "shape": "box" if "rug" not in label.lower() and "carpet" not in label.lower() else "plane",
            "position": [round(pos_x, 3), round(pos_y, 3), round(pos_z, 3)],
            "size": self._size_for_label(label),
            "rotation": [0, 10 if idx % 2 else -10, 0],
            "color": "#8b8b8b",
            "material": "default",
            "roughness": 0.62,
            "metalness": 0.2,
            "interaction": self._interaction_for_label(label),
            "asset_ref": f"/Game/RealmCast/Generated/{slug}",
            "asset_variant": "default",
            "material_slots": ["base"],
            "collider_type": "box",
            "nav_blocker": "rug" not in label.lower() and "carpet" not in label.lower(),
            "interaction_anchor": {"x": round(pos_x, 3), "y": 0.85, "z": round(pos_z, 3)},
            "animation_profile": None,
            "audio_profile": "roomtone",
            "lod_group": "generated",
            "spawn_tags": ["generated", "fallback", slug],
            "children": [],
        }

    def _post_process_scene(self, scene: dict[str, Any], selected_frames: list[dict[str, Any]]) -> dict[str, Any]:
        label_counts, _ = self._collect_label_stats(selected_frames)
        room = scene.setdefault("room", {})
        room["width"] = max(float(room.get("width", 0) or 0), 10.0)
        room["depth"] = max(float(room.get("depth", 0) or 0), 9.0)
        room["height"] = max(float(room.get("height", 0) or 0), 3.0)
        room.setdefault("floor_color", "#676767")
        room.setdefault("wall_color", "#d1d5db")
        room.setdefault("ceiling_color", "#f3f4f6")

        objects = scene.get("objects")
        if not isinstance(objects, list):
            objects = []
            scene["objects"] = objects

        # Keep center navigable: nudge large blockers away from center lane.
        for obj in objects:
            if not isinstance(obj, dict):
                continue
            name = str(obj.get("name") or "Object").strip() or "Object"
            obj["name"] = name
            pos = obj.get("position") or [0, 0, 0]
            if not isinstance(pos, list) or len(pos) < 3:
                pos = [0, 0, 0]
            size = obj.get("size") or [0.7, 0.9, 0.6]
            if not isinstance(size, list) or len(size) < 3:
                size = [0.7, 0.9, 0.6]
            try:
                x, y, z = float(pos[0]), float(pos[1]), float(pos[2])
                sx, _, sz = float(size[0]), float(size[1]), float(size[2])
            except Exception:
                x, y, z = 0.0, 0.0, 0.0
                sx, sz = 0.7, 0.6
            if obj.get("nav_blocker", True) and abs(x) < 1.2 and abs(z) < 1.4 and (sx > 0.75 or sz > 0.75):
                x = 2.8 if x >= 0 else -2.8
                z = 2.5 if z >= 0 else -2.5
            obj["position"] = [round(x, 3), round(y, 3), round(z, 3)]

        has_door = any("door" in str(obj.get("name", "")).lower() for obj in objects if isinstance(obj, dict))
        if self._needs_connection_door(label_counts) and not has_door:
            objects.append(
                {
                    "name": "Connecting Door",
                    "shape": "box",
                    "position": [0.0, 1.05, -4.35],
                    "size": [1.1, 2.1, 0.14],
                    "rotation": [0, 0, 0],
                    "color": "#8b6b4c",
                    "material": "wood",
                    "roughness": 0.58,
                    "metalness": 0.08,
                    "interaction": "open",
                    "asset_ref": "/Game/RealmCast/Generated/connecting_door",
                    "asset_variant": "default",
                    "material_slots": ["frame", "panel"],
                    "collider_type": "box",
                    "nav_blocker": True,
                    "interaction_anchor": {"x": 0.0, "y": 1.0, "z": -4.1},
                    "animation_profile": "hinge_open",
                    "audio_profile": "door_wood",
                    "lod_group": "furniture",
                    "spawn_tags": ["generated", "connector", "door"],
                    "children": [],
                }
            )

        people = scene.get("people")
        if not isinstance(people, list):
            people = []
            scene["people"] = people

        wanted_people = self._estimated_person_count(label_counts)
        if wanted_people <= 0:
            scene["people"] = []
        else:
            base_people = [p for p in people if isinstance(p, dict)]
            if not base_people:
                base_people = [
                    {
                        "name": "DetectedPerson_1",
                        "position": [-1.2, 0.0, -1.4],
                        "pose": "standing",
                        "facing": 145,
                        "height": 1.72,
                        "shirt_color": "#3b82f6",
                        "pants_color": "#1f2937",
                        "skin_color": "#d7b08a",
                    }
                ]
            while len(base_people) < wanted_people:
                i = len(base_people) + 1
                base_people.append(
                    {
                        **base_people[0],
                        "name": f"DetectedPerson_{i}",
                        "position": [round(-1.8 + (i * 1.3), 3), 0.0, round(-1.6 + (i * 0.7), 3)],
                        "facing": (120 + (i * 35)) % 360,
                    }
                )
            scene["people"] = base_people[:wanted_people]

        return scene

    def _fallback_scene(self, selected_frames: list[dict[str, Any]]) -> dict[str, Any]:
        label_counts, _ = self._collect_label_stats(selected_frames)
        style_cues = self._infer_style_cues(label_counts)
        room_width = 10.6
        room_depth = 9.4

        perimeter_slots = [
            (-4.3, 0.45, -3.4), (-3.1, 0.45, -3.5), (-1.9, 0.45, -3.5), (-0.6, 0.45, -3.45),
            (0.7, 0.45, -3.45), (2.0, 0.45, -3.5), (3.3, 0.45, -3.45), (4.2, 0.45, -2.2),
            (4.2, 0.45, -0.8), (4.2, 0.45, 0.7), (4.2, 0.45, 2.2),
            (3.3, 0.45, 3.35), (2.0, 0.45, 3.35), (0.7, 0.45, 3.35), (-0.6, 0.45, 3.4),
            (-1.9, 0.45, 3.35), (-3.1, 0.45, 3.35), (-4.2, 0.45, 2.0), (-4.2, 0.45, 0.6), (-4.2, 0.45, -1.0),
        ]

        objects: list[dict[str, Any]] = []
        ignored = {"wall", "floor", "ceiling", "person", "human", "room", "indoor", "window"}
        labels: list[str] = []
        for label, count in label_counts.most_common(12):
            lx = label.lower().strip()
            if not lx or any(token == lx for token in ignored):
                continue
            repeat = min(4, max(1, count // 2 if count > 1 else 1))
            labels.extend([label] * repeat)

        if not labels:
            labels = [
                "desk", "chair", "chair", "shelf", "lamp", "cabinet", "plant", "monitor", "table", "rug", "door",
            ]

        for idx, slot in enumerate(perimeter_slots[: max(14, len(labels))]):
            label = labels[idx % len(labels)]
            pos_x, pos_y, pos_z = slot
            suffix = f" {idx + 1}" if labels.count(label) > 1 else ""
            name = f"{label.title()}{suffix}"
            objects.append(self._make_object(name=name, label=label, pos_x=pos_x, pos_y=pos_y, pos_z=pos_z, idx=idx))

        objects.extend(
            [
                {
                    "name": "Area Rug",
                    "shape": "plane",
                    "position": [0, 0.01, 0],
                    "size": [3.6, 0.01, 2.6],
                    "rotation": [0, 0, 0],
                    "color": "#635d54",
                    "material": "fabric",
                    "roughness": 0.88,
                    "metalness": 0.02,
                    "interaction": "none",
                    "asset_ref": "/Game/RealmCast/Generated/area_rug",
                    "asset_variant": "neutral",
                    "material_slots": ["base"],
                    "collider_type": "box",
                    "nav_blocker": False,
                    "interaction_anchor": {"x": 0, "y": 0.05, "z": 0},
                    "animation_profile": None,
                    "audio_profile": "none",
                    "lod_group": "decor",
                    "spawn_tags": ["generated", "decor"],
                    "children": [],
                },
                {
                    "name": "Wall Art Cluster",
                    "shape": "box",
                    "position": [-4.85, 1.7, -0.1],
                    "size": [0.05, 1.0, 1.3],
                    "rotation": [0, 90, 0],
                    "color": "#bba782",
                    "material": "wood",
                    "roughness": 0.5,
                    "metalness": 0.08,
                    "interaction": "none",
                    "asset_ref": "/Game/RealmCast/Generated/wall_art_cluster",
                    "asset_variant": "gallery",
                    "material_slots": ["frame", "canvas"],
                    "collider_type": "box",
                    "nav_blocker": False,
                    "interaction_anchor": {"x": -4.7, "y": 1.5, "z": -0.1},
                    "animation_profile": None,
                    "audio_profile": "none",
                    "lod_group": "decor",
                    "spawn_tags": ["generated", "decor"],
                    "children": [],
                },
                {
                    "name": "Hidden Mac Mini",
                    "shape": "box",
                    "position": [3.95, 0.22, 2.95],
                    "size": [0.22, 0.04, 0.22],
                    "rotation": [0, 18, 0],
                    "color": "#9ca3af",
                    "material": "aluminum",
                    "roughness": 0.25,
                    "metalness": 0.85,
                    "interaction": "use",
                    "asset_ref": "/Game/RealmCast/Generated/hidden_mac_mini",
                    "asset_variant": "space_gray",
                    "material_slots": ["shell"],
                    "collider_type": "box",
                    "nav_blocker": False,
                    "interaction_anchor": {"x": 3.95, "y": 0.35, "z": 2.95},
                    "animation_profile": None,
                    "audio_profile": "device_hum",
                    "lod_group": "small_props",
                    "spawn_tags": ["generated", "mission_target", "hidden_mac_mini"],
                    "children": [],
                },
            ]
        )

        wanted_people = self._estimated_person_count(label_counts)
        people = []
        for i in range(wanted_people):
            people.append(
                {
                    "name": f"DetectedPerson_{i + 1}",
                    "position": [round(-1.6 + (i * 1.4), 3), 0.0, round(-1.4 + (i * 0.8), 3)],
                    "pose": "standing",
                    "facing": (145 + i * 40) % 360,
                    "height": 1.72,
                    "shirt_color": ["#3b82f6", "#ef4444", "#10b981"][i % 3],
                    "pants_color": "#1f2937",
                    "skin_color": "#d7b08a",
                }
            )

        style_hint = style_cues[0] if style_cues else "modern room"
        wall_color = "#d8d2c8" if "office" in style_hint else "#d1d5db"

        scene = {
            "room": {
                "width": room_width,
                "depth": room_depth,
                "height": 3.1,
                "floor_color": "#676767",
                "wall_color": wall_color,
                "ceiling_color": "#f3f4f6",
            },
            "lights": [
                {"type": "ambient", "color": "#fffdf6", "intensity": 0.52},
                {"type": "directional", "color": "#ffe7c4", "intensity": 1.12, "position": [3.3, 3.9, -1.2]},
                {"type": "point", "color": "#ffc58f", "intensity": 0.72, "position": [-2.9, 2.6, 1.8]},
            ],
            "objects": objects,
            "people": people,
        }
        return self._post_process_scene(scene, selected_frames)

    def _build_raw_frame_parts(self, selected_frames: list[dict[str, Any]]) -> list[Any]:
        parts: list[Any] = []
        for frame in selected_frames:
            frame_path = Path(str(frame.get("frame_path") or "")).expanduser()
            if not frame_path.exists() or not frame_path.is_file():
                continue

            try:
                blob = frame_path.read_bytes()
            except Exception:
                continue

            mime_type = mimetypes.guess_type(str(frame_path))[0] or "image/jpeg"
            parts.append(types.Part.from_bytes(data=blob, mime_type=mime_type))

        return parts

    def generate_scene_from_segments(self, selected_frames: list[dict[str, Any]]) -> dict[str, Any]:
        if not selected_frames:
            return self._fallback_scene(selected_frames)

        scene_context = self._build_scene_context(selected_frames)
        prompt = SCENE_PROMPT.format(scene_context=scene_context)

        if not self.enabled:
            return self._fallback_scene(selected_frames)

        frame_parts = self._build_raw_frame_parts(selected_frames)
        if not frame_parts:
            return self._fallback_scene(selected_frames)

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=[prompt, *frame_parts],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.34,
                ),
            )
            parsed = json.loads((response.text or "").strip())
            return self._post_process_scene(parsed, selected_frames)
        except Exception:
            return self._fallback_scene(selected_frames)
