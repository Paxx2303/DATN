from __future__ import annotations

import io
import json
import math
import re
import time
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Optional, Tuple

import requests
import numpy as np
from PIL import Image, ImageDraw, ImageOps


class StreamType(Enum):
    """Enum for camera stream types"""
    YOUTUBE_LIVE = "youtube_live"
    HTTP_SNAPSHOT = "http_snapshot"


YOUTUBE_EMBED_PATTERN = re.compile(r"https?://www\.youtube\.com/embed/([A-Za-z0-9_-]{6,})")
CAMERA_TITLE_PATTERN = re.compile(r"Camera[^<\n\r]{0,120}")


def sanitize_camera_title(raw: str, *, fallback: str) -> str:
    """Strip HTML junk often captured by CAMERA_TITLE_PATTERN (e.g. alt='Camera' />)."""
    t = raw.strip()
    t = re.sub(r'["\']?\s*/>.*$', "", t)
    t = t.strip(" \"'")
    t = re.sub(r"\s+", " ", t)
    if len(t) < 2 or t in ('"', "'", "/>"):
        return fallback
    return t[:120]


@dataclass
class ExternalCameraItem:
    index: int
    embed_url: str
    youtube_id: str
    title: str
    snapshot_url: str
    stream_type: StreamType = StreamType.YOUTUBE_LIVE
    priority: int = 1
    coordinates: Optional[Tuple[float, float]] = None


def extract_camera_entries(page_url: str, limit: int = 6, timeout: int = 20) -> list[ExternalCameraItem]:
    response = requests.get(page_url, timeout=timeout)
    response.raise_for_status()
    html = response.text

    iframe_matches = re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    title_matches = CAMERA_TITLE_PATTERN.findall(html)

    entries: list[ExternalCameraItem] = []
    for index, iframe_url in enumerate(iframe_matches):
        youtube_match = YOUTUBE_EMBED_PATTERN.search(iframe_url)
        if not youtube_match:
            continue

        youtube_id = youtube_match.group(1)
        raw_title = title_matches[index] if index < len(title_matches) else ""
        title = sanitize_camera_title(raw_title, fallback=f"Camera {len(entries) + 1}")
        snapshot_url = f"https://i.ytimg.com/vi/{youtube_id}/hqdefault_live.jpg"
        entries.append(
            ExternalCameraItem(
                index=len(entries),
                embed_url=iframe_url,
                youtube_id=youtube_id,
                title=title,
                snapshot_url=snapshot_url,
            )
        )
        if len(entries) >= limit:
            break

    return entries


def _cache_bust(url: str) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={int(time.time() * 1000)}"


def download_camera_snapshot(entry: ExternalCameraItem, timeout: int = 20) -> Image.Image:
    candidates = [
        f"https://i.ytimg.com/vi/{entry.youtube_id}/maxresdefault_live.jpg",
        f"https://i.ytimg.com/vi/{entry.youtube_id}/hqdefault_live.jpg",
        f"https://i.ytimg.com/vi/{entry.youtube_id}/hqdefault.jpg",
        f"https://i.ytimg.com/vi/{entry.youtube_id}/mqdefault.jpg",
    ]

    no_cache_headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}

    last_error: Exception | None = None
    for snapshot_url in candidates:
        try:
            fetch_url = _cache_bust(snapshot_url)
            response = requests.get(fetch_url, timeout=timeout, headers=no_cache_headers)
            response.raise_for_status()
            image = Image.open(io.BytesIO(response.content))
            image.load()
            entry.snapshot_url = snapshot_url
            return image.convert("RGB")
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"Unable to download snapshot for {entry.youtube_id}: {last_error}")


def capture_stream_frame(stream_url: str, warmup_frames: int = 3) -> Image.Image:
    try:
        import cv2
    except Exception as exc:
        raise RuntimeError(f"OpenCV import failed while opening stream: {exc}") from exc

    capture = cv2.VideoCapture(stream_url)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError(f"Unable to open stream source: {stream_url}")

    try:
        frame = None
        for _ in range(max(1, warmup_frames)):
            ok, candidate = capture.read()
            if ok and candidate is not None:
                frame = candidate
        if frame is None:
            raise RuntimeError(f"Unable to read frame from stream source: {stream_url}")

        if frame.ndim != 3:
            raise RuntimeError("Unsupported stream frame shape.")

        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(np.asarray(frame_rgb), mode="RGB")
        image.load()
        return image
    finally:
        capture.release()


def build_camera_collage(items: list[dict[str, Any]], cell_size: tuple[int, int] = (640, 360)) -> Image.Image:
    columns = 2
    rows = max(1, math.ceil(len(items) / columns))
    margin = 16
    width = columns * cell_size[0] + (columns + 1) * margin
    height = rows * cell_size[1] + (rows + 1) * margin

    canvas = Image.new("RGB", (width, height), "#08131c")
    draw = ImageDraw.Draw(canvas)

    for index, item in enumerate(items):
        row = index // columns
        column = index % columns
        x = margin + column * (cell_size[0] + margin)
        y = margin + row * (cell_size[1] + margin)

        image = item["annotated_image"].copy()
        image.thumbnail(cell_size, Image.Resampling.LANCZOS)
        pad_x = x + (cell_size[0] - image.width) // 2
        pad_y = y + (cell_size[1] - image.height) // 2

        panel = Image.new("RGB", cell_size, "#10202c")
        panel_draw = ImageDraw.Draw(panel)
        panel_draw.rounded_rectangle((0, 0, cell_size[0] - 1, cell_size[1] - 1), radius=18, outline="#1f394b", width=2)
        panel.paste(image, ((cell_size[0] - image.width) // 2, (cell_size[1] - image.height) // 2))
        canvas.paste(panel, (x, y))

        label = f"{item['title']} | {item['total_objects']} obj"
        draw.rounded_rectangle((x + 14, y + 14, x + min(cell_size[0] - 14, 14 + len(label) * 9), y + 44), radius=10, fill="#08131c")
        draw.text((x + 24, y + 22), label, fill="#edf5fb")

    return canvas


def serialize_camera_item(item: ExternalCameraItem) -> dict:
    """Convert ExternalCameraItem dataclass to JSON-serializable dict."""
    data = asdict(item)
    # Convert enum to string
    data['stream_type'] = item.stream_type.value
    return data


def deserialize_camera_item(data: dict) -> ExternalCameraItem:
    """Parse dict to ExternalCameraItem dataclass, raise ValueError if required fields missing."""
    required_fields = {'index', 'embed_url', 'youtube_id', 'title', 'snapshot_url'}
    if not required_fields.issubset(data.keys()):
        missing = required_fields - set(data.keys())
        raise ValueError(f"Missing required fields: {missing}")
    
    # Convert stream_type string back to enum
    stream_type_value = data.get('stream_type', 'youtube_live')
    try:
        stream_type = StreamType(stream_type_value)
    except ValueError:
        raise ValueError(f"Invalid stream_type: {stream_type_value}")
    
    return ExternalCameraItem(
        index=data['index'],
        embed_url=data['embed_url'],
        youtube_id=data['youtube_id'],
        title=data['title'],
        snapshot_url=data['snapshot_url'],
        stream_type=stream_type,
        priority=data.get('priority', 1),
        coordinates=data.get('coordinates', None)
    )
