from __future__ import annotations

import base64
import json
import os
import random
import time
from dataclasses import dataclass
from io import BytesIO
from typing import Any

import httpx
from PIL import Image, ImageDraw


@dataclass
class OvershootSegmentResult:
    label: str
    confidence: float
    bbox: list[float]
    polygon: list[list[float]]
    mask_b64: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class OvershootFrameResult:
    objects: list[OvershootSegmentResult]
    raw: dict[str, Any]


class OvershootAdapter:
    """Configurable adapter for unknown API contracts.

    Supported adapters:
    - generic_v1: {image_base64, include_masks} -> {objects: [{label, confidence, bbox, polygon, mask}]}
    - vlm_v1: {image:{content,type}} -> {segments:[{class_name,score,box,points,mask_b64}]}
    """

    def __init__(self, adapter_name: str = "generic_v1") -> None:
        self.adapter_name = adapter_name

    def build_payload(self, image_b64: str, filename: str) -> dict[str, Any]:
        if self.adapter_name == "vlm_v1":
            return {
                "image": {
                    "content": image_b64,
                    "type": "base64",
                    "filename": filename,
                },
                "return_masks": True,
                "return_polygons": True,
            }

        # generic_v1 default
        return {
            "image_base64": image_b64,
            "filename": filename,
            "include_masks": True,
            "include_polygons": True,
            "task": "segmentation",
        }

    def parse_response(self, payload: dict[str, Any]) -> OvershootFrameResult:
        raw_objects = payload.get("objects") or payload.get("segments") or payload.get("detections") or []
        objects: list[OvershootSegmentResult] = []
        for item in raw_objects:
            label = item.get("label") or item.get("class") or item.get("class_name") or "unknown"
            confidence = float(item.get("confidence") or item.get("score") or 0.0)
            bbox = item.get("bbox") or item.get("box") or []
            polygon = item.get("polygon") or item.get("points") or item.get("contour") or []
            mask_b64 = item.get("mask") or item.get("mask_b64")
            if isinstance(bbox, dict):
                bbox = [bbox.get("x", 0), bbox.get("y", 0), bbox.get("w", 0), bbox.get("h", 0)]
            bbox = [float(v) for v in bbox][:4] if isinstance(bbox, list) else []
            if isinstance(polygon, list) and polygon and isinstance(polygon[0], dict):
                polygon = [[float(p.get("x", 0)), float(p.get("y", 0))] for p in polygon]
            polygon = [[float(p[0]), float(p[1])] for p in polygon] if isinstance(polygon, list) else []

            objects.append(
                OvershootSegmentResult(
                    label=str(label),
                    confidence=max(0.0, min(1.0, confidence)),
                    bbox=bbox,
                    polygon=polygon,
                    mask_b64=mask_b64,
                    metadata={
                        k: v
                        for k, v in item.items()
                        if k not in {"label", "class", "class_name", "confidence", "score", "bbox", "box", "polygon", "points", "contour", "mask", "mask_b64"}
                    },
                )
            )

        return OvershootFrameResult(objects=objects, raw=payload)


class OvershootClient:
    def __init__(self) -> None:
        self.api_key = os.getenv("OVERSHOOT_API_KEY", "").strip()
        self.base_url = os.getenv("OVERSHOOT_BASE_URL", "https://api.overshoot.ai").rstrip("/")
        self.segment_path = os.getenv("OVERSHOOT_SEGMENT_PATH", "/v1/segment")
        self.timeout_sec = float(os.getenv("OVERSHOOT_TIMEOUT_SEC", "45"))
        self.max_retries = int(os.getenv("OVERSHOOT_MAX_RETRIES", "3"))
        self.mock_mode = os.getenv("OVERSHOOT_MOCK_MODE", "").lower() in {"1", "true", "yes", "on"} or not self.api_key
        self.adapter = OvershootAdapter(os.getenv("OVERSHOOT_ADAPTER", "generic_v1"))
        self.mock_on_error = os.getenv("OVERSHOOT_MOCK_ON_ERROR", "true").lower() in {"1", "true", "yes", "on"}

    def _segment_live(self, image_path: str) -> OvershootFrameResult:
        with open(image_path, "rb") as f:
            raw_bytes = f.read()
        image_b64 = base64.b64encode(raw_bytes).decode("utf-8")
        payload = self.adapter.build_payload(image_b64=image_b64, filename=os.path.basename(image_path))

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        url = f"{self.base_url}{self.segment_path}"

        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            try:
                with httpx.Client(timeout=self.timeout_sec) as client:
                    response = client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                result = response.json()
                if isinstance(result, str):
                    result = json.loads(result)
                return self.adapter.parse_response(result)
            except Exception as exc:  # pragma: no cover - network path
                last_exc = exc
                if attempt >= self.max_retries:
                    break
                backoff = min(5.0, 0.75 * attempt)
                time.sleep(backoff)
        raise RuntimeError(f"Overshoot segmentation failed after retries: {last_exc}")

    def _random_bbox(self, w: int, h: int) -> list[float]:
        bw = random.uniform(0.12, 0.35) * w
        bh = random.uniform(0.12, 0.35) * h
        x = random.uniform(0, max(1.0, w - bw))
        y = random.uniform(0, max(1.0, h - bh))
        return [x, y, bw, bh]

    def _segment_mock(self, image_path: str) -> OvershootFrameResult:
        image = Image.open(image_path).convert("RGB")
        w, h = image.size
        candidate_labels = ["wall", "floor", "table", "chair", "person", "monitor", "door", "window", "sofa", "lamp"]
        random.seed(os.path.basename(image_path))

        object_count = 4 + random.randint(0, 3)
        objects: list[OvershootSegmentResult] = []
        for idx in range(object_count):
            label = random.choice(candidate_labels)
            bbox = self._random_bbox(w, h)
            x, y, bw, bh = bbox
            polygon = [
                [x, y],
                [x + bw, y],
                [x + bw, y + bh],
                [x, y + bh],
            ]
            objects.append(
                OvershootSegmentResult(
                    label=label,
                    confidence=round(random.uniform(0.55, 0.96), 3),
                    bbox=[round(v, 2) for v in bbox],
                    polygon=[[round(p[0], 2), round(p[1], 2)] for p in polygon],
                    mask_b64=None,
                    metadata={"mock": True, "instance_id": f"{label}-{idx}"},
                )
            )

        return OvershootFrameResult(
            objects=objects,
            raw={"mode": "mock", "count": len(objects)},
        )

    def segment_frame(self, image_path: str) -> OvershootFrameResult:
        if self.mock_mode:
            return self._segment_mock(image_path)
        try:
            return self._segment_live(image_path)
        except Exception:
            if self.mock_on_error:
                return self._segment_mock(image_path)
            raise


def _decode_base64_bytes(data: str) -> bytes:
    raw = data.strip()
    if "," in raw and raw.startswith("data:"):
        raw = raw.split(",", 1)[1]
    raw += "=" * ((4 - len(raw) % 4) % 4)
    return base64.b64decode(raw)


def _decode_mask_image(mask_b64: str) -> Image.Image | None:
    try:
        data = _decode_base64_bytes(mask_b64)
    except Exception:
        return None

    try:
        img = Image.open(BytesIO(data))
        if "A" in img.mode:
            return img.getchannel("A")
        return img.convert("L")
    except Exception:
        return None


def _normalize_bbox(raw_bbox: list[float], image_size: tuple[int, int]) -> tuple[float, float, float, float] | None:
    if len(raw_bbox) != 4:
        return None

    w, h = image_size
    x1, y1, v3, v4 = [float(v) for v in raw_bbox]

    # Normalized xywh.
    if 0 <= x1 <= 1 and 0 <= y1 <= 1 and 0 <= v3 <= 1 and 0 <= v4 <= 1:
        x1 *= w
        y1 *= h
        bw = v3 * w
        bh = v4 * h
        return x1, y1, max(1.0, bw), max(1.0, bh)

    # xyxy style box where v3/v4 are bottom-right corner.
    if v3 > x1 and v4 > y1 and v3 <= w * 1.25 and v4 <= h * 1.25:
        return x1, y1, max(1.0, v3 - x1), max(1.0, v4 - y1)

    # Assume xywh pixels.
    return x1, y1, max(1.0, v3), max(1.0, v4)


def _normalize_polygon(raw_polygon: list[list[float]], image_size: tuple[int, int]) -> list[tuple[float, float]]:
    if not raw_polygon:
        return []
    w, h = image_size
    points: list[tuple[float, float]] = []
    for p in raw_polygon:
        if not isinstance(p, (list, tuple)) or len(p) < 2:
            continue
        x = float(p[0])
        y = float(p[1])
        if 0 <= x <= 1 and 0 <= y <= 1:
            x *= w
            y *= h
        points.append((x, y))
    return points


def render_overlay(image_path: str, objects: list[OvershootSegmentResult], out_path: str) -> None:
    image = Image.open(image_path).convert("RGB")
    composed = image.convert("RGBA")

    palette = [
        (255, 99, 132),
        (54, 162, 235),
        (255, 206, 86),
        (75, 192, 192),
        (153, 102, 255),
        (255, 159, 64),
    ]

    for i, obj in enumerate(objects):
        color = palette[i % len(palette)]

        mask_img = _decode_mask_image(obj.mask_b64) if obj.mask_b64 else None
        if mask_img is not None:
            if mask_img.size != image.size:
                resampling = Image.Resampling.NEAREST if hasattr(Image, "Resampling") else Image.NEAREST
                mask_img = mask_img.resize(image.size, resample=resampling)
            alpha_mask = mask_img.point(lambda px: int(px * 0.35))
            tint = Image.new("RGBA", image.size, color + (0,))
            tint.putalpha(alpha_mask)
            composed = Image.alpha_composite(composed, tint)

        draw = ImageDraw.Draw(composed)
        polygon = _normalize_polygon(obj.polygon, image.size)
        bbox = _normalize_bbox(obj.bbox, image.size)

        if polygon and len(polygon) >= 3:
            draw.polygon(polygon, fill=color + (45,), outline=color + (220,))
            anchor_x, anchor_y = polygon[0]
        elif bbox:
            x, y, bw, bh = bbox
            draw.rectangle([(x, y), (x + bw, y + bh)], fill=color + (35,), outline=color + (220,), width=2)
            anchor_x, anchor_y = x, y
        else:
            anchor_x, anchor_y = 12, 12 + (18 * i)

        label = f"{obj.label} {obj.confidence:.2f}"
        draw.text((anchor_x + 4, anchor_y + 4), label, fill=(255, 255, 255, 255))

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    composed.convert("RGB").save(out_path, quality=95)


def write_mask_from_bbox(image_size: tuple[int, int], bbox: list[float], out_path: str) -> None:
    mask = Image.new("L", image_size, 0)
    draw = ImageDraw.Draw(mask)
    normalized = _normalize_bbox(bbox, image_size)
    if normalized:
        x, y, w, h = normalized
        draw.rectangle([(x, y), (x + w, y + h)], fill=255)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    mask.save(out_path)


def write_mask_from_base64(mask_b64: str, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    mask_image = _decode_mask_image(mask_b64)
    if mask_image is not None:
        mask_image.convert("L").save(out_path)
        return

    data = _decode_base64_bytes(mask_b64)
    with open(out_path, "wb") as f:
        f.write(data)
