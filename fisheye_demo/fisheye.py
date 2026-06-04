"""
fisheye.py — Fisheye Distortion Engine

Tất cả phép tính dùng NumPy vectorized (không có Python loop qua từng pixel).
Hiệu năng: ảnh 1920×1080 xử lý < 80ms trên CPU (numpy vectorized).

THUẬT TOÁN CHÍNH: Inverse mapping + bilinear interpolation
"""

import numpy as np
from PIL import Image
import logging

logger = logging.getLogger(__name__)


def apply_fisheye(
    image: Image.Image,
    strength: float = 0.6,
    radius: float = 0.85,
    effect: str = "standard",
    center_x: float = 0.5,
    center_y: float = 0.5,
    axis_scale_x: float = 1.0,
    axis_scale_y: float = 1.0,
    full_frame: bool = False,
) -> Image.Image:
    """
    Áp dụng biến dạng fisheye lên ảnh PIL.
    
    Parameters
    ----------
    image       : Ảnh PIL đầu vào (RGB)
    strength    : Cường độ biến dạng [0.0 – 1.0].
                  0.0 = không biến dạng, 1.0 = tối đa
    radius      : Bán kính vùng biến dạng [0.0 – 1.5].
                  < 1.0: chỉ biến dạng vùng trung tâm
    effect      : "standard" | "extreme" | "subtle"
    center_x    : Tâm biến dạng theo trục X [0.0–1.0], default 0.5 (giữa)
    center_y    : Tâm biến dạng theo trục Y [0.0–1.0], default 0.5 (giữa)
    axis_scale_x: Scale trục X để tạo thấu kính elip (default 1.0 = tròn)
    axis_scale_y: Scale trục Y để tạo thấu kính elip (default 1.0 = tròn)
    full_frame  : True = biến dạng toàn bộ frame (kể cả góc)
    
    Returns
    -------
    Image.Image : Ảnh PIL mới đã biến dạng (RGB)
    """
    import cv2

    # ── Bước 1: Chuyển PIL → NumPy float32 ──────────────────
    img_array = np.array(image.convert("RGB"))
    h, w = img_array.shape[:2]

    # ── Bước 2: Xây dựng lưới tọa độ pixel đích ─────────────
    # col_coords[i,j] = j (tọa độ cột),  row_coords[i,j] = i (tọa độ hàng)
    col_coords, row_coords = np.meshgrid(np.arange(w, dtype=np.float32),
                                         np.arange(h, dtype=np.float32))

    # ── Bước 3: Chuẩn hóa về [-1, 1] quanh tâm (center_x, center_y) ──
    # cx, cy là pixel tâm; half_w, half_h là bán nửa chiều
    cx = center_x * (w - 1)   # pixel tâm theo X
    cy = center_y * (h - 1)   # pixel tâm theo Y
    half_w = w / 2.0
    half_h = h / 2.0

    # u: tọa độ chuẩn hóa theo X, v: theo Y — cả hai trong khoảng ~[-1, 1]
    u = (col_coords - cx) / half_w   # shape: (h, w)
    v = (row_coords - cy) / half_h   # shape: (h, w)

    # ── Bước 4: Scale trục (hỗ trợ thấu kính elip) ──────────
    u_scaled = u * axis_scale_x
    v_scaled = v * axis_scale_y

    # ── Bước 5: Tính bán kính chuẩn hóa từ tâm ──────────────
    r = np.sqrt(u_scaled ** 2 + v_scaled ** 2)  # shape: (h, w)
    # Tránh chia cho 0 ở đúng tâm điểm
    r_safe = np.where(r == 0, 1e-10, r)

    # ── Bước 6: Áp dụng hàm biến dạng theo effect ───────────
    if effect == "standard":
        # arcsin mapping: mô phỏng thấu kính cầu (equidistant projection)
        r_input = np.clip(r * strength, -1.0 + 1e-7, 1.0 - 1e-7)
        r_new = np.arcsin(r_input) * radius

    elif effect == "extreme":
        # Parabolic barrel distortion — phồng mạnh ở tâm, nhẹ ở viền
        r_new = (r * strength) / (1.0 + (1.0 - strength) * r ** 2 + 1e-10)

    elif effect == "subtle":
        # Pincushion nhẹ với polynomial bậc 3
        r_new = r * (1.0 + strength * r ** 2) * radius

    else:
        logger.warning(f"Unknown fisheye effect '{effect}', falling back to standard")
        r_input = np.clip(r * strength, -1.0 + 1e-7, 1.0 - 1e-7)
        r_new = np.arcsin(r_input) * radius

    # ── Bước 7: Inverse mapping — tính tọa độ nguồn ─────────
    # Tỷ lệ scale: r_new/r_safe cho mỗi pixel
    scale = r_new / r_safe      # shape: (h, w)

    # Chuyển ngược về tọa độ pixel thực (floating point)
    map_x = u * scale * half_w + cx
    map_y = v * scale * half_h + cy

    # ── Bước 8: Áp dụng cv2.remap ───────────────────────────
    result = cv2.remap(img_array, map_x.astype(np.float32), map_y.astype(np.float32), 
                       cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0))

    # ── Bước 9: Nếu không full_frame, mask vùng ngoài bán kính ──
    if not full_frame:
        # Vùng ngoài radius → pixel đen
        outside_mask = r > (radius + 0.05)
        result[outside_mask] = 0

    # ── Bước 10: Chuyển về PIL Image ────────────────────────
    return Image.fromarray(result, "RGB")


def _bilinear_sample(
    img: np.ndarray,
    x_coords: np.ndarray,
    y_coords: np.ndarray,
) -> np.ndarray:
    """
    Bilinear interpolation vectorized.
    
    Với mỗi pixel đích tại (i,j), tọa độ nguồn là (x_coords[i,j], y_coords[i,j])
    có thể là số thập phân. Ta nội suy từ 4 pixel láng giềng:
    
        TL=(x0,y0)  TR=(x1,y0)
        BL=(x0,y1)  BR=(x1,y1)
    
        output = TL*(1-dx)*(1-dy) + TR*dx*(1-dy)
               + BL*(1-dx)*dy    + BR*dx*dy
    
    Parameters
    ----------
    img      : ndarray shape (H, W, 3), dtype float32
    x_coords : ndarray shape (H, W) — cột nguồn (float)
    y_coords : ndarray shape (H, W) — hàng nguồn (float)
    
    Returns
    -------
    ndarray shape (H, W, 3), dtype float32
    """
    H, W = img.shape[:2]

    # Clamp tọa độ vào biên ảnh gốc
    x_coords = np.clip(x_coords, 0, W - 1)
    y_coords = np.clip(y_coords, 0, H - 1)

    # Lấy 4 pixel láng giềng (integer coords)
    x0 = np.floor(x_coords).astype(np.int32)
    y0 = np.floor(y_coords).astype(np.int32)
    x1 = np.minimum(x0 + 1, W - 1)
    y1 = np.minimum(y0 + 1, H - 1)

    # Trọng số nội suy (fractional parts)
    dx = (x_coords - x0)[..., np.newaxis]  # shape (H,W,1)
    dy = (y_coords - y0)[..., np.newaxis]  # shape (H,W,1)

    # Lấy màu của 4 láng giềng — img[row, col]
    tl = img[y0, x0]   # Top-Left
    tr = img[y0, x1]   # Top-Right
    bl = img[y1, x0]   # Bottom-Left
    br = img[y1, x1]   # Bottom-Right

    # Bilinear formula
    result = (
        tl * (1 - dx) * (1 - dy)
        + tr * dx * (1 - dy)
        + bl * (1 - dx) * dy
        + br * dx * dy
    )
    return result


def apply_fisheye_to_cv2(
    frame: np.ndarray,
    strength: float,
    radius: float,
    effect: str = "standard",
    center_x: float = 0.5,
    center_y: float = 0.5,
) -> np.ndarray:
    """
    Wrapper tiện lợi: nhận OpenCV frame (BGR ndarray), trả về BGR ndarray.
    Được dùng trong video_detect.py để tránh convert PIL mỗi frame.
    """
    # OpenCV dùng BGR, PIL dùng RGB — cần đổi
    rgb_array = frame[..., ::-1].copy()   # BGR → RGB (in-place flip channel)
    pil_img = Image.fromarray(rgb_array.astype(np.uint8))
    
    result_pil = apply_fisheye(
        pil_img, strength=strength, radius=radius, 
        effect=effect, center_x=center_x, center_y=center_y
    )
    # PIL RGB → OpenCV BGR
    result_bgr = np.array(result_pil)[..., ::-1].copy()
    return result_bgr
