"""
routes/examples.py — Example traffic-scene image generator

Routes:
  GET /api/examples            → list of scenarios (JSON)
  GET /api/examples/<name>.jpg → generated JPEG image
"""

import io
import logging
import random
from flask import Blueprint, send_file, jsonify
from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)
examples_bp = Blueprint("examples", __name__, url_prefix="/api/examples")

_SCENARIOS = [
    {"key": "normal",       "title": "Bình thường",   "desc": "5–8 xe, thưa thớt"},
    {"key": "congestion",   "title": "Ùn tắc",         "desc": "20+ xe dày đặc"},
    {"key": "fisheye",      "title": "Góc fisheye",    "desc": "Camera biến dạng barrel"},
    {"key": "highway",      "title": "Cao tốc",        "desc": "4 làn xe, tốc độ cao"},
    {"key": "night",        "title": "Ban đêm",        "desc": "Đèn pha, nền tối"},
    {"key": "intersection", "title": "Giao lộ",        "desc": "4 hướng, xe chen nhau"},
]

# In-memory cache so images are only generated once
_CACHE: dict[str, bytes] = {}

_CAR_COLORS = [
    (210, 55, 55),   (55, 110, 220),  (55, 190, 95),
    (220, 175, 55),  (175, 175, 175), (38, 38, 38),
    (240, 240, 240), (200, 95, 45),   (130, 55, 200),
]


@examples_bp.route("")
@examples_bp.route("/")
def list_examples():
    return jsonify(_SCENARIOS)


@examples_bp.route("/<scenario>.jpg")
def get_example_image(scenario: str):
    valid_keys = {s["key"] for s in _SCENARIOS}
    if scenario not in valid_keys:
        return jsonify({"error": "Unknown scenario"}), 404

    if scenario not in _CACHE:
        img = _gen_scene(scenario)
        buf = io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=92)
        _CACHE[scenario] = buf.getvalue()

    return send_file(
        io.BytesIO(_CACHE[scenario]),
        mimetype="image/jpeg",
        download_name=f"{scenario}_example.jpg",
    )


# ── Image generators ─────────────────────────────────────────────────────────

def _road_canvas(w: int, h: int, lanes: int = 2, night: bool = False) -> tuple:
    """Return (Image, ImageDraw) with a road drawn."""
    road_gray = (40, 40, 45) if night else (75, 80, 88)
    sky_color  = (10, 12, 18) if night else (48, 52, 60)
    img   = Image.new("RGB", (w, h), sky_color)
    draw  = ImageDraw.Draw(img)
    mx    = w // 6
    draw.rectangle([mx, 0, w - mx, h], fill=road_gray)
    # Lane dividers
    lane_w = (w - 2 * mx) // lanes
    for i in range(1, lanes):
        lx = mx + i * lane_w
        clr = (200, 195, 75) if not night else (160, 155, 60)
        for y in range(0, h, 40):
            draw.rectangle([lx - 2, y, lx + 2, y + 18], fill=clr)
    # Centre line
    cx = w // 2
    for y in range(0, h, 20):
        draw.rectangle([cx - 1, y, cx + 1, y + 9],
                        fill=(210, 210, 210) if not night else (130, 130, 130))
    return img, draw


def _car(draw: ImageDraw.ImageDraw, x: int, y: int,
         w: int = 44, h: int = 70, color=(200, 60, 60)):
    draw.rectangle([x, y, x + w, y + h], fill=color, outline=(0, 0, 0))
    # Windshield
    sw, sh = int(w * 0.62), int(h * 0.24)
    draw.rectangle([x + (w - sw)//2, y + int(h * 0.14),
                    x + (w + sw)//2, y + int(h * 0.14) + sh],
                   fill=tuple(min(255, c + 60) for c in color))


def _gen_scene(scenario: str) -> Image.Image:
    W, H = 640, 480
    rng = random.Random({"normal": 42, "congestion": 7, "fisheye": 42,
                          "highway": 13, "night": 99, "intersection": 55}.get(scenario, 1))

    if scenario == "normal":
        img, draw = _road_canvas(W, H, lanes=2)
        for i in range(6):
            x = rng.randint(115, 430)
            y = i * 72 + rng.randint(8, 28)
            if y + 74 > H: continue
            _car(draw, x, y, color=rng.choice(_CAR_COLORS))

    elif scenario == "congestion":
        img, draw = _road_canvas(W, H, lanes=3)
        cols = [120, 178, 238, 298, 358, 420]
        for row in range(7):
            for cx in cols:
                x = cx + rng.randint(-7, 7)
                y = row * 62 + rng.randint(0, 10)
                if y + 68 > H: continue
                _car(draw, x, y, 42, 64, color=rng.choice(_CAR_COLORS))

    elif scenario == "highway":
        img, draw = _road_canvas(W, H, lanes=4)
        lanes_x = [105, 200, 300, 398]
        for lx in lanes_x:
            for j in range(3):
                y = j * 135 + rng.randint(10, 38)
                if y + 82 > H: continue
                is_truck = rng.random() < 0.3
                w, h = (42, 95) if is_truck else (38, 62)
                _car(draw, lx, y, w, h, color=rng.choice(_CAR_COLORS))

    elif scenario == "night":
        img, draw = _road_canvas(W, H, lanes=2, night=True)
        for i in range(5):
            x = rng.randint(115, 430)
            y = i * 88 + rng.randint(0, 22)
            if y + 72 > H: continue
            col = rng.choice(_CAR_COLORS)
            _car(draw, x, y, 44, 72, color=col)
            # Headlights
            for ox in (6, 30):
                draw.ellipse([x + ox, y - 8, x + ox + 10, y + 2],
                             fill=(255, 255, 185))
        # Ambient glow
        for _ in range(20):
            gx, gy = rng.randint(0, W), rng.randint(0, H)
            draw.ellipse([gx - 2, gy - 2, gx + 2, gy + 2],
                         fill=(255, 255, 100, 80))

    elif scenario == "fisheye":
        img, draw = _road_canvas(W, H, lanes=2)
        for i in range(8):
            x = rng.randint(90, 460)
            y = i * 55 + rng.randint(5, 20)
            if y + 64 > H: continue
            _car(draw, x, y, 40, 66, color=rng.choice(_CAR_COLORS))
        try:
            from fisheye import apply_fisheye
            img = apply_fisheye(img, strength=0.72, radius=0.88, effect="standard")
        except Exception:
            pass

    elif scenario == "intersection":
        img = Image.new("RGB", (W, H), (50, 54, 60))
        draw = ImageDraw.Draw(img)
        road_c = (78, 83, 90)
        # Horizontal + vertical roads
        draw.rectangle([0, H // 3, W, 2 * H // 3], fill=road_c)
        draw.rectangle([W // 3, 0, 2 * W // 3, H], fill=road_c)
        # Cross-box
        draw.rectangle([W // 3, H // 3, 2 * W // 3, 2 * H // 3], fill=(72, 76, 83))
        # Vehicles from 4 sides
        groups = [
            [(80, H//2 + 18), (150, H//2 + 18), (220, H//2 + 18)],
            [(W//2 + 18, 32), (W//2 + 18, 108), (W//2 + 18, 172)],
            [(W - 82, H//2 - 90), (W - 150, H//2 - 90)],
            [(W//2 - 56, H - 78), (W//2 - 56, H - 162)],
        ]
        for group in groups:
            for px, py in group:
                _car(draw, px, py, 44, 70, color=rng.choice(_CAR_COLORS))
    else:
        img = Image.new("RGB", (W, H), (28, 30, 38))

    return img
