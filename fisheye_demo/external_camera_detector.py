"""
external_camera_detector.py — Public Camera Discovery & Snapshot Capture

HAI MODE:
1. snapshot: Parse HTML để tìm <img> tags có src kết thúc bằng .jpg/.jpeg
2. stream:   Connect đến HLS/RTSP stream và chụp khung hình

THIẾT KẾ:
- Sử dụng BeautifulSoup để parse HTML.
- Tải ảnh song song với ThreadPoolExecutor.
- Trả về list[CameraEntry] với url, name, snapshot_image (PIL Image).
"""

import requests
import logging
import io
import cv2
import numpy as np
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional
from PIL import Image
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 10   # seconds


@dataclass
class CameraEntry:
    url: str                        # URL của snapshot JPG
    name: str = ""                  # Tên camera (từ alt text hoặc URL)
    camera_index: int = 0
    snapshot: Optional[Image.Image] = field(default=None, repr=False)


def extract_camera_entries(
    source_url: str,
    limit: int = 6,
) -> list[CameraEntry]:
    """
    Phân tích HTML của trang web camera giao thông và trả về danh sách entries.

    Tìm kiếm theo thứ tự ưu tiên:
    1. <img src/data-src/data-original/data-lazy-src>
    2. <a href> links dẫn đến ảnh
    3. CSS background-image: url(...)
    4. URL patterns trong <script> blocks

    Parameters
    ----------
    source_url : URL của trang web camera (vd: https://camera.0511.vn/camera.html)
    limit      : Giới hạn số camera lấy về

    Returns
    -------
    list[CameraEntry] — Danh sách camera entries (chưa có snapshot image)
    """
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        }
        resp = requests.get(source_url, headers=headers, timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch camera page {source_url}: {e}")
        return []

    soup = BeautifulSoup(resp.text, "lxml")
    entries: list[CameraEntry] = []
    seen_urls: set[str] = set()

    # ── Attributes to check on <img> tags (lazy-load patterns) ──
    _IMG_SRC_ATTRS = (
        "src", "data-src", "data-original",
        "data-lazy-src", "data-url", "data-image",
    )
    _IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".gif")
    _CAMERA_KEYWORDS = ("snap", "snapshot", "cam", "camera", "live", "view",
                        "stream", "cctv", "traffic", "webcam")

    def _looks_like_camera_url(url: str) -> bool:
        lo = url.lower()
        has_ext = any(lo.endswith(e) for e in _IMAGE_EXTS)
        has_kw  = any(kw in lo for kw in _CAMERA_KEYWORDS)
        return has_ext or has_kw

    def _add_entry(raw_url: str, name: str = "") -> bool:
        if not raw_url or raw_url.startswith("data:"):
            return False
        full = _resolve_url(source_url, raw_url)
        if full in seen_urls:
            return False
        seen_urls.add(full)
        entries.append(CameraEntry(
            url=full,
            name=name or f"Camera {len(entries) + 1}",
            camera_index=len(entries),
        ))
        return True

    # ── 0.5 <iframe> youtube embeds ──────────────────────────
    for iframe in soup.find_all("iframe"):
        src = iframe.get("src", "")
        if "youtube.com/embed/" in src:
            import urllib.parse
            parsed_src = urllib.parse.urlparse(src)
            video_id = parsed_src.path.split("/")[-1]
            if video_id:
                thumb_url = f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
                
                # Attempt to find a meaningful title from nearby text
                name = iframe.get("title", "").strip()
                if not name:
                    # Look for preceding header or text
                    prev = iframe.find_previous(["h1", "h2", "h3", "h4", "p", "div"])
                    if prev and prev.get_text(strip=True):
                        name = prev.get_text(strip=True)
                
                _add_entry(thumb_url, name or f"YouTube Live {video_id}")
        if len(entries) >= limit:
            break

    # ── 1. <img> tags — check multiple src attributes ────────
    if len(entries) < limit:
        for img_tag in soup.find_all("img"):
            src = ""
            for attr in _IMG_SRC_ATTRS:
                val = img_tag.get(attr, "").strip()
                if val:
                    src = val
                    break
            if not src:
                continue
            name = (img_tag.get("alt") or img_tag.get("title") or "").strip()
            if _looks_like_camera_url(src):
                _add_entry(src, name)
            if len(entries) >= limit:
                break

    # ── 2. <a href> image links ──────────────────────────────
    if len(entries) < limit:
        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if _looks_like_camera_url(href):
                name = a_tag.get_text(strip=True) or ""
                _add_entry(href, name)
            if len(entries) >= limit:
                break

    # ── 3. CSS background-image: url(...) on any tag ────────
    if len(entries) < limit:
        import re
        for tag in soup.find_all(style=True):
            matches = re.findall(
                r'url\(["\']?(https?://[^"\')\s]+)["\']?\)',
                tag.get("style", ""),
            )
            for raw in matches:
                if _looks_like_camera_url(raw):
                    _add_entry(raw)
                if len(entries) >= limit:
                    break
            if len(entries) >= limit:
                break

    # ── 4. Script tag — regex hunt for camera image URLs ────
    if len(entries) < limit:
        import re
        _URL_RE = re.compile(
            r'(?:"|\'|=)(https?://[^\s"\'<>]+?(?:'
            r'\.jpg|\.jpeg|\.png|snapshot|snap\.cgi|live\.jpg|cam\d|camera\d|'
            r'/cam/|/cctv/|/traffic/)(?:[^\s"\'<>]*)?)(?:"|\')',
            re.IGNORECASE,
        )
        for script in soup.find_all("script"):
            text = script.string or ""
            for m in _URL_RE.finditer(text):
                url = m.group(1).rstrip("\\")
                if _looks_like_camera_url(url):
                    _add_entry(url)
                if len(entries) >= limit:
                    break
            if len(entries) >= limit:
                break

    logger.info(f"Discovered {len(entries)} camera entries from {source_url}")
    return entries[:limit]


def fetch_snapshots_parallel(
    entries: list[CameraEntry],
    max_workers: int = 4,
) -> list[CameraEntry]:
    """
    Tải ảnh snapshot cho tất cả entries song song.
    Cập nhật trường .snapshot của mỗi entry.
    
    Returns danh sách entries (chỉ những entry tải thành công).
    """
    results = []
    
    def _fetch_one(entry: CameraEntry) -> Optional[CameraEntry]:
        try:
            resp = requests.get(entry.url, timeout=REQUEST_TIMEOUT, stream=True)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content)).convert("RGB")
            entry.snapshot = img
            return entry
        except Exception as e:
            logger.warning(f"Failed to fetch snapshot {entry.url}: {e}")
            return None
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, e): e for e in entries}
        for future in as_completed(futures):
            result = future.result()
            if result is not None:
                results.append(result)
    
    return results


def capture_stream_frame(stream_url: str) -> Optional[Image.Image]:
    """
    Chụp một frame từ luồng HLS/RTSP/MJPEG.
    
    Sử dụng OpenCV VideoCapture để kết nối đến stream URL.
    """
    cap = cv2.VideoCapture(stream_url)
    if not cap.isOpened():
        logger.error(f"Cannot connect to stream: {stream_url}")
        return None
    
    try:
        ret, frame = cap.read()
        if not ret or frame is None:
            logger.warning(f"Empty frame from stream: {stream_url}")
            return None
        
        # BGR → RGB → PIL
        rgb = frame[..., ::-1]
        return Image.fromarray(rgb.astype(np.uint8))
    finally:
        cap.release()


def build_camera_collage(
    entries: list[CameraEntry],
    cell_width: int = 320,
    cell_height: int = 240,
    cols: int = 2,
    labels: Optional[dict[int, str]] = None,
) -> Image.Image:
    """
    Tạo ảnh lưới (collage) từ nhiều camera snapshot.
    
    Layout: cols × ceil(n/cols) grid, mỗi cell được resize về cell_width × cell_height.
    
    Parameters
    ----------
    entries    : List CameraEntry với .snapshot đã được load
    labels     : dict[camera_index → label_text] để overlay lên từng cell
    
    Returns
    -------
    PIL Image ảnh lưới tổng hợp
    """
    valid = [e for e in entries if e.snapshot is not None]
    if not valid:
        # Trả về ảnh đen nếu không có camera nào
        return Image.new("RGB", (cell_width * cols, cell_height), color=(20, 20, 20))
    
    rows = (len(valid) + cols - 1) // cols
    canvas_w = cell_width * cols
    canvas_h = cell_height * rows
    
    canvas = Image.new("RGB", (canvas_w, canvas_h), color=(15, 15, 20))
    
    for i, entry in enumerate(valid):
        row = i // cols
        col = i % cols
        x = col * cell_width
        y = row * cell_height
        
        # Resize snapshot để fit cell
        thumb = entry.snapshot.copy()
        thumb.thumbnail((cell_width, cell_height), Image.LANCZOS)
        
        # Center trong cell
        paste_x = x + (cell_width - thumb.width) // 2
        paste_y = y + (cell_height - thumb.height) // 2
        canvas.paste(thumb, (paste_x, paste_y))
        
        # Overlay label
        if labels and entry.camera_index in labels:
            _draw_label_on_pil(canvas, labels[entry.camera_index], x, y)
    
    return canvas


def _draw_label_on_pil(img: Image.Image, text: str, x: int, y: int) -> None:
    """Vẽ text label lên góc trên trái của cell."""
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img)
    # Background rectangle
    draw.rectangle([x, y, x + len(text)*8 + 10, y + 22], fill=(0, 0, 0, 180))
    draw.text((x + 5, y + 4), text, fill=(0, 255, 150))


def _resolve_url(base_url: str, relative_url: str) -> str:
    """Giải quyết URL tương đối về URL tuyệt đối."""
    from urllib.parse import urljoin
    return urljoin(base_url, relative_url)
