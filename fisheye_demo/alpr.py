"""
alpr.py — Automatic License Plate Recognition (Nhận diện biển số tự động)

PHƯƠNG PHÁP:
- Không có model phát hiện biển số riêng → tận dụng YOLO phát hiện phương tiện,
  cắt vùng xe rồi chạy OCR (EasyOCR) trên crop để tìm chuỗi giống biển số.
- Chuẩn hoá kết quả OCR về định dạng biển số Việt Nam (vd: 51F-123.45, 29X1-234.56).

THIẾT KẾ:
- EasyOCR được nạp LAZY và TÙY CHỌN: nếu chưa cài / không tải được model,
  is_available() = False và toàn hệ thống vẫn chạy bình thường (degrade gracefully).
- Thread-safe khi khởi tạo reader.
"""

import re
import logging
import threading
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

# Ngưỡng OCR
_MIN_OCR_CONF = 0.30        # bỏ qua text OCR có độ tin cậy quá thấp
_MIN_PLATE_LEN = 7          # số ký tự alnum tối thiểu của 1 biển hợp lệ
_MAX_PLATE_LEN = 10

# Regex biển số VN sau khi đã bỏ ký tự phân cách & viết hoa:
#   2 số tỉnh + 1-2 chữ (seri) + (1 số seri tùy chọn, LAZY) + 4-5 số đăng ký
#   \d?? lazy → ưu tiên dạng phổ biến "1 chữ + 5 số" (ô tô) vd 51F-123.45
_VN_PLATE_RE = re.compile(r"^(\d{2})([A-Z]{1,2})(\d??)(\d{4,5})$")


def normalize_vn_plate(raw: str) -> Optional[str]:
    """
    Chuẩn hoá chuỗi OCR thô về biển số VN. Trả None nếu không khớp định dạng.

    Ví dụ:  '51F12345'  → '51F-123.45'
            '29 X1 2345'→ '29X1-2345'
            '30A-1234'  → '30A-1234'
    """
    if not raw:
        return None
    # Bỏ mọi ký tự không phải chữ/số, viết hoa; sửa nhầm lẫn OCR phổ biến
    s = re.sub(r"[^A-Za-z0-9]", "", raw).upper()
    if not (_MIN_PLATE_LEN <= len(s) <= _MAX_PLATE_LEN):
        return None

    m = _VN_PLATE_RE.match(s)
    if not m:
        return None
    province, letters, series_digit, number = m.groups()
    head = f"{province}{letters}{series_digit}"
    # 5 số → nhóm 3.2 (123.45); 4 số → giữ nguyên
    tail = f"{number[:3]}.{number[3:]}" if len(number) == 5 else number
    return f"{head}-{tail}"


class PlateRecognizer:
    """Nhận diện biển số dựa trên EasyOCR (lazy, optional)."""

    def __init__(self, languages: Optional[list] = None, gpu: bool = False):
        self._languages = languages or ["en"]
        self._gpu = gpu
        self._reader = None
        self._init_failed = False
        self._lock = threading.Lock()

    # ── Trạng thái ────────────────────────────────────────────────────────────

    def _ensure_reader(self):
        """Nạp EasyOCR reader một lần (lazy). Trả None nếu không khả dụng."""
        if self._reader is not None or self._init_failed:
            return self._reader
        with self._lock:
            if self._reader is not None or self._init_failed:
                return self._reader
            try:
                import easyocr  # noqa: WPS433 (import cục bộ, optional)
                self._reader = easyocr.Reader(self._languages, gpu=self._gpu)
                logger.info("EasyOCR reader initialised (langs=%s, gpu=%s)",
                            self._languages, self._gpu)
            except Exception as exc:  # ImportError hoặc lỗi tải model
                self._init_failed = True
                logger.warning("ALPR không khả dụng (EasyOCR init failed): %s", exc)
            return self._reader

    def is_available(self) -> bool:
        return self._ensure_reader() is not None

    # ── Nhận diện ─────────────────────────────────────────────────────────────

    def _ocr_plate_from_crop(self, crop_bgr: np.ndarray) -> Optional[tuple]:
        """OCR 1 crop, trả (plate_text, confidence) hoặc None."""
        reader = self._ensure_reader()
        if reader is None or crop_bgr is None or crop_bgr.size == 0:
            return None
        try:
            results = reader.readtext(crop_bgr)
        except Exception as exc:
            logger.debug("OCR readtext error: %s", exc)
            return None

        # Ứng viên: từng đoạn text + chuỗi nối tất cả (biển 2 dòng)
        candidates: list[tuple[str, float]] = []
        joined_parts = []
        joined_conf = []
        for _box, text, conf in results:
            if conf < _MIN_OCR_CONF:
                continue
            candidates.append((text, float(conf)))
            joined_parts.append(text)
            joined_conf.append(float(conf))
        if joined_parts:
            candidates.append(("".join(joined_parts),
                               float(np.mean(joined_conf))))

        best = None
        for text, conf in candidates:
            plate = normalize_vn_plate(text)
            if plate and (best is None or conf > best[1]):
                best = (plate, round(conf, 3))
        return best

    @staticmethod
    def _plate_candidates(x1: int, y1: int, x2: int, y2: int) -> list[tuple]:
        """
        Trả về các vùng con để OCR trong 1 khung xe:
          1. Cả khung xe (fallback).
          2. Vùng biển: phần dưới 55% × giữa 60% chiều rộng (nơi biển thường nằm).
        Lấy conf cao nhất giữa các vùng → không bao giờ tệ hơn chỉ-OCR-cả-xe.
        """
        w = x2 - x1
        h = y2 - y1
        cands = [(x1, y1, x2, y2)]
        bx1 = x1 + int(w * 0.20)
        bx2 = x2 - int(w * 0.20)
        by1 = y1 + int(h * 0.45)
        if (bx2 - bx1) >= 16 and (y2 - by1) >= 16:
            cands.append((bx1, by1, bx2, y2))
        return cands

    def recognize(self, frame_bgr: np.ndarray,
                  vehicle_boxes: Optional[list] = None) -> list[dict]:
        """
        Nhận diện biển số trên 1 frame BGR.

        Parameters
        ----------
        frame_bgr     : ảnh OpenCV BGR
        vehicle_boxes : list[{"bbox":[x1,y1,x2,y2], "vehicle_type":str}] (tùy chọn).
                        Nếu None → OCR toàn ảnh.

        Returns
        -------
        list[{plate, confidence, bbox, vehicle_type}]
        """
        if not self.is_available() or frame_bgr is None:
            return []

        h, w = frame_bgr.shape[:2]
        plates: list[dict] = []
        seen: set[str] = set()

        regions = vehicle_boxes if vehicle_boxes else [
            {"bbox": [0, 0, w, h], "vehicle_type": "unknown"}
        ]

        for region in regions:
            bbox = region.get("bbox") or [0, 0, w, h]
            x1 = max(0, int(bbox[0])); y1 = max(0, int(bbox[1]))
            x2 = min(w, int(bbox[2])); y2 = min(h, int(bbox[3]))
            if x2 - x1 < 16 or y2 - y1 < 16:
                continue

            # OCR cả vùng xe LẪN vùng biển (phần dưới-giữa khung xe), lấy conf cao hơn.
            # Vùng biển giúp đọc biển vừa/nhỏ; cả-xe là fallback cho biển nhỏ/lệch vị trí.
            best = None  # (plate_text, conf, bbox)
            for cb_x1, cb_y1, cb_x2, cb_y2 in self._plate_candidates(x1, y1, x2, y2):
                result = self._ocr_plate_from_crop(frame_bgr[cb_y1:cb_y2, cb_x1:cb_x2])
                if result is None:
                    continue
                if best is None or result[1] > best[1]:
                    best = (result[0], result[1], [cb_x1, cb_y1, cb_x2, cb_y2])
            if best is None:
                continue
            plate_text, conf, plate_bbox = best
            if plate_text in seen:
                continue
            seen.add(plate_text)
            plates.append({
                "plate": plate_text,
                "confidence": conf,
                "bbox": plate_bbox,
                "vehicle_type": region.get("vehicle_type", "unknown"),
            })
        return plates


def annotate_plates_on_frame(frame_bgr: np.ndarray, plates: list[dict]) -> np.ndarray:
    """Vẽ khung + chuỗi biển số lên frame BGR."""
    import cv2
    for p in plates:
        bbox = p.get("bbox") or []
        if len(bbox) < 4:
            continue
        x1, y1, x2, y2 = (int(v) for v in bbox[:4])
        label = f"{p['plate']} ({p['confidence']:.2f})"
        cv2.rectangle(frame_bgr, (x1, y1), (x2, y2), (0, 215, 255), 2)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)
        ty = max(y1 - 6, th + 6)
        cv2.rectangle(frame_bgr, (x1, ty - th - 6), (x1 + tw + 6, ty + 2),
                      (0, 215, 255), -1)
        cv2.putText(frame_bgr, label, (x1 + 3, ty - 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2)
    return frame_bgr


class FastALPRRecognizer:
    """
    Engine ALPR 2 tầng dùng fast-alpr: YOLO phát hiện BIỂN SỐ riêng + OCR chuyên biển.
    Tốt hơn EasyOCR thô (không cần crop vùng xe). Lazy + optional (fallback nếu thiếu).
    Cùng interface với PlateRecognizer: is_available(), recognize(frame_bgr, vehicle_boxes).
    """

    def __init__(self):
        self._alpr = None
        self._init_failed = False
        self._lock = threading.Lock()

    def _ensure(self):
        if self._alpr is not None or self._init_failed:
            return self._alpr
        with self._lock:
            if self._alpr is not None or self._init_failed:
                return self._alpr
            try:
                from fast_alpr import ALPR
                self._alpr = ALPR(
                    detector_model="yolo-v9-t-384-license-plate-end2end",
                    ocr_model="global-plates-mobile-vit-v2-model",
                )
                logger.info("fast-alpr engine initialised")
            except Exception as exc:
                self._init_failed = True
                logger.warning("fast-alpr không khả dụng: %s", exc)
            return self._alpr

    def is_available(self) -> bool:
        return self._ensure() is not None

    def recognize(self, frame_bgr: np.ndarray,
                  vehicle_boxes: Optional[list] = None) -> list[dict]:
        """fast-alpr tự phát hiện biển trên cả frame (không cần vehicle_boxes)."""
        alpr = self._ensure()
        if alpr is None or frame_bgr is None:
            return []
        try:
            results = alpr.predict(frame_bgr)
        except Exception as exc:
            logger.debug("fast-alpr predict error: %s", exc)
            return []
        plates: list[dict] = []
        seen: set[str] = set()
        for r in results:
            ocr = getattr(r, "ocr", None)
            if ocr is None or not getattr(ocr, "text", None):
                continue
            raw = ocr.text
            plate = normalize_vn_plate(raw) or re.sub(r"[^A-Za-z0-9]", "", raw).upper()
            if not plate or plate in seen:
                continue
            seen.add(plate)
            c = ocr.confidence
            conf = float(np.mean(c)) if isinstance(c, (list, tuple)) else float(c)
            bb = r.detection.bounding_box
            plates.append({
                "plate": plate,
                "confidence": round(conf, 3),
                "bbox": [int(bb.x1), int(bb.y1), int(bb.x2), int(bb.y2)],
                "vehicle_type": "unknown",
            })
        return plates


def _select_recognizer():
    """Chọn engine ALPR theo env ALPR_ENGINE (fast_alpr|easyocr). Fallback EasyOCR."""
    import os
    # Mặc định EasyOCR (đã chứng minh ổn định). Đặt ALPR_ENGINE=fast_alpr để thử
    # engine 2 tầng (plate-detector + OCR chuyên biển) — tốt hơn ở ảnh cận cảnh THẬT.
    engine = os.getenv("ALPR_ENGINE", "easyocr").strip().lower()
    if engine in ("fast_alpr", "fastalpr", "fast-alpr"):
        try:
            import fast_alpr  # noqa: F401 — chỉ kiểm tra đã cài
            logger.info("ALPR engine = fast-alpr")
            return FastALPRRecognizer()
        except ImportError:
            logger.warning("fast-alpr chưa cài → dùng EasyOCR")
    return PlateRecognizer()


# Singleton dùng chung toàn hệ thống
plate_recognizer = _select_recognizer()
