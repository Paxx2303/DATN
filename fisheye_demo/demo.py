"""
FishEye8K — YOLO11 Detection Demo (Streamlit version)
Run: streamlit run demo.py
"""

import time
import io
from pathlib import Path

import streamlit as st
import numpy as np
from PIL import Image

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="FishEye8K · YOLO11 Demo",
    page_icon="🐟",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Class config ─────────────────────────────────────────────────────────────
CLASS_NAMES = ["Car", "Bus", "Truck", "Pedestrian", "Motorbike"]
CLASS_COLORS_BGR = {
    "Car":        (247, 195, 79),
    "Bus":        (74, 183, 255),
    "Truck":      (80, 83, 239),
    "Pedestrian": (107, 214, 165),
    "Motorbike":  (216, 147, 206),
}
CLASS_COLORS_HEX = {
    "Car":        "#4FC3F7",
    "Bus":        "#FFB74D",
    "Truck":      "#EF5350",
    "Pedestrian": "#A5D6A7",
    "Motorbike":  "#CE93D8",
}

# ── FIX 1: Default checkpoint path (raw string để xử lý dấu cách + ngoặc) ──
DEFAULT_WEIGHTS = r"C:\Using\NCKH\yolo11_fisheye_v5_best.pt"

# ── Custom CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&family=JetBrains+Mono&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
section[data-testid="stSidebar"] {
    background: #0f131d !important;
    border-right: 1px solid rgba(255,255,255,.06) !important;
}
.hero-title {
    font-size: 2.6rem; font-weight: 800; letter-spacing: -1px;
    background: linear-gradient(135deg, #fff 0%, #4FC3F7 50%, #7C4DFF 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    background-clip: text; margin-bottom: 4px;
}
.hero-sub { color: #7B8BA5; font-size: 1rem; margin-bottom: 28px; }
.metric-card {
    background: rgba(21,27,41,.85);
    border: 1px solid rgba(255,255,255,.08);
    border-radius: 14px; padding: 18px 20px; text-align: center;
}
.metric-num  { font-size: 2rem; font-weight: 800; line-height: 1; }
.metric-label { font-size: 0.72rem; color: #7B8BA5; font-weight: 600;
                text-transform: uppercase; letter-spacing: .8px; margin-top: 4px; }
.det-badge {
    display: inline-block; padding: 3px 10px; border-radius: 20px;
    font-size: 0.75rem; font-weight: 600; margin: 2px 3px;
}
.panel-hdr {
    font-size: .78rem; font-weight: 700; text-transform: uppercase;
    letter-spacing: .9px; color: #7B8BA5; margin-bottom: 10px;
}
</style>
""", unsafe_allow_html=True)


# ── FIX 2: Model loader — KHÔNG dùng @st.cache_resource với path arg ─────────
# cache_resource cache theo hash của args → nếu path thay đổi sẽ reload đúng
# Nhưng cần dùng key riêng để tránh reload không cần thiết
def _load_model_internal(weights_path: str):
    """Internal loader, gọi thẳng không cache để tránh stale."""
    from ultralytics import YOLO
    import torch

    # Ưu tiên: path người dùng nhập → DEFAULT_WEIGHTS → fallback yolo11n
    candidates = []
    if weights_path and weights_path.strip():
        candidates.append(Path(weights_path.strip()))
    candidates.append(Path(DEFAULT_WEIGHTS))
    candidates += [
        Path("best.pt"),
        Path(__file__).parent / "best.pt",
        Path(__file__).parent.parent / "best.pt",
    ]

    for p in candidates:
        if p.exists():
            try:
                model = YOLO(str(p))
                # Override tên class về FishEye8K
                model.model.names = {i: n for i, n in enumerate(CLASS_NAMES)}
                return model, str(p), True
            except Exception as e:
                st.warning(f"Không load được {p.name}: {e}")
                continue

    # Fallback COCO demo
    model = YOLO("yolo11n.pt")
    return model, "yolo11n.pt (COCO demo)", False


@st.cache_resource(show_spinner=False)
def load_model_cached(weights_path: str):
    """Cached theo weights_path string — tự reload khi path thay đổi."""
    return _load_model_internal(weights_path)


# ── FIX 3: Device detection (không hardcode CPU) ──────────────────────────────
def get_device() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return "0"
    except ImportError:
        pass
    return "cpu"

DEVICE = get_device()


# ── Inference ────────────────────────────────────────────────────────────────
def run_inference(model, pil_img: Image.Image, conf: float, iou: float):
    import cv2

    img_np  = np.array(pil_img.convert("RGB"))
    img_bgr = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)

    t0 = time.perf_counter()
    results = model.predict(
        source=img_bgr, conf=conf, iou=iou,
        verbose=False, device=DEVICE,
    )[0]
    elapsed_ms = (time.perf_counter() - t0) * 1000

    annotated    = img_np.copy()
    detections   = []
    class_counts = {c: 0 for c in CLASS_NAMES}

    NAME_MAP = {
        "car": "Car", "bus": "Bus", "truck": "Truck",
        "person": "Pedestrian", "motorcycle": "Motorbike", "bicycle": "Motorbike",
    }

    if results.boxes is not None and len(results.boxes):
        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            conf_val = float(box.conf[0])
            cls_id   = int(box.cls[0])
            raw_name = model.model.names.get(cls_id, str(cls_id))
            cls_name = NAME_MAP.get(raw_name.lower(), raw_name)

            color_bgr = CLASS_COLORS_BGR.get(cls_name, (200, 200, 200))
            color_hex = CLASS_COLORS_HEX.get(cls_name, "#aaaaaa")

            cv2.rectangle(annotated, (x1, y1), (x2, y2), color_bgr, 3)
            label = f"{cls_name} {conf_val:.0%}"
            (tw, th), bl = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.65, 2)
            lx, ly = x1, max(y1 - 10, th + 6)
            cv2.rectangle(annotated, (lx, ly - th - 4), (lx + tw + 8, ly + bl), color_bgr, -1)
            cv2.putText(annotated, label, (lx + 4, ly - 2),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 0), 2)

            if cls_name in class_counts:
                class_counts[cls_name] += 1

            detections.append({
                "class":      cls_name,
                "confidence": round(conf_val, 3),
                "bbox":       (x1, y1, x2, y2),
                "color":      color_hex,
            })

    return Image.fromarray(annotated), detections, class_counts, elapsed_ms


# ════════════════════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## 🐟 FishEye8K Demo")
    st.markdown("**YOLO11-L** Object Detection\non Fisheye Camera Images")
    st.divider()

    st.markdown("### ⚙️ Model")
    custom_path = st.text_input(
        "Custom weights (.pt path)",
        value=DEFAULT_WEIGHTS,          # ← hiện sẵn path checkpoint mới
        help="Đường dẫn tới file best.pt của bạn"
    )

    st.divider()
    st.markdown("### 🎚️ Detection Settings")
    conf_thresh = st.slider("Confidence threshold", 0.05, 0.95, 0.25, 0.05, format="%.2f")
    iou_thresh  = st.slider("NMS IoU threshold",    0.10, 0.90, 0.45, 0.05, format="%.2f")

    st.divider()
    st.markdown("### 🏷️ Target Classes")
    for cls in CLASS_NAMES:
        c = CLASS_COLORS_HEX[cls]
        st.markdown(
            f'<span class="det-badge" style="background:{c}22;border:1px solid {c};color:{c}">'
            f'● {cls}</span>',
            unsafe_allow_html=True,
        )

    st.divider()
    # Hiện device đang dùng
    st.caption(f"Device: {'🟢 GPU (CUDA)' if DEVICE != 'cpu' else '🟡 CPU'}")
    st.caption("Model: YOLO11-L · Dataset: FishEye8K\n"
               "80 epochs resume · checkpoint v5")


# ════════════════════════════════════════════════════════════════════════════
# MAIN PAGE
# ════════════════════════════════════════════════════════════════════════════
st.markdown('<div class="hero-title">Fisheye Object Detection</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="hero-sub">Upload a fisheye camera image — YOLO11-L will detect '
    'Car · Bus · Truck · Pedestrian · Motorbike in real-time.</div>',
    unsafe_allow_html=True,
)

# Load model (cache theo path → reload tự động khi đổi path)
with st.spinner("Loading YOLO11 model..."):
    model, model_path, is_custom = load_model_cached(custom_path)

if is_custom:
    st.success(f"✅ Custom model loaded: `{Path(model_path).name}`", icon="🎯")
else:
    st.info(
        "⚠️ Using **yolo11n.pt** (COCO demo). "
        "Paste đường dẫn `best.pt` vào sidebar để dùng model FishEye8K.",
        icon="💡",
    )

st.divider()

# ── FIX 4: Upload — clear session state khi ảnh mới được upload ──────────────
uploaded = st.file_uploader(
    "📂 Upload a Fisheye Image",
    type=["jpg", "jpeg", "png", "bmp", "tiff", "webp"],
    help="Drag & drop hoặc click để chọn ảnh. Tối đa 32 MB.",
)

# Xóa kết quả cũ khi upload ảnh mới
if uploaded is not None:
    _upload_key = f"{uploaded.name}_{uploaded.size}"
    if st.session_state.get("_upload_key") != _upload_key:
        st.session_state.pop("last_result", None)
        st.session_state["_upload_key"] = _upload_key

if uploaded is None:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="text-align:center;padding:60px 0;color:#4B5568">
            <div style="font-size:72px;margin-bottom:16px">📷</div>
            <div style="font-size:1.1rem;font-weight:600;color:#718096">
                Drop a fisheye image above to get started
            </div>
            <div style="font-size:.85rem;margin-top:8px;color:#A0AEC0">
                Supports JPG · PNG · BMP · TIFF · WEBP
            </div>
        </div>
        """, unsafe_allow_html=True)
    st.stop()

# ── Process ───────────────────────────────────────────────────────────────────
pil_img = Image.open(uploaded).convert("RGB")
w_orig, h_orig = pil_img.size

col_orig, col_res = st.columns(2)
with col_orig:
    st.markdown('<div class="panel-hdr">📷 Original Fisheye Image</div>',
                unsafe_allow_html=True)
    st.image(pil_img, use_container_width=True,
             caption=f"{uploaded.name}  ({w_orig}×{h_orig})")

run_btn = st.button("⚡  Detect Objects", type="primary", use_container_width=True)

if run_btn or st.session_state.get("last_result"):
    if run_btn:
        with st.spinner("🔍 Running YOLO11 inference..."):
            annotated, detections, class_counts, elapsed_ms = run_inference(
                model, pil_img, conf_thresh, iou_thresh
            )
        st.session_state["last_result"] = {
            "annotated":    annotated,
            "detections":   detections,
            "class_counts": class_counts,
            "elapsed_ms":   elapsed_ms,
        }

    res          = st.session_state["last_result"]
    annotated    = res["annotated"]
    detections   = res["detections"]
    class_counts = res["class_counts"]
    elapsed_ms   = res["elapsed_ms"]

    with col_res:
        fps = round(1000 / elapsed_ms) if elapsed_ms > 0 else 0
        st.markdown('<div class="panel-hdr">🎯 YOLO11 Detection Result</div>',
                    unsafe_allow_html=True)
        st.image(annotated, use_container_width=True,
                 caption=f"Inference: {elapsed_ms:.1f} ms · {fps} FPS")

    st.divider()

    # ── Metrics ───────────────────────────────────────────────────────────────
    st.markdown("### 📊 Detection Statistics")
    metric_cols = st.columns(len(CLASS_NAMES) + 2)
    for i, cls in enumerate(CLASS_NAMES):
        cnt   = class_counts.get(cls, 0)
        color = CLASS_COLORS_HEX[cls]
        metric_cols[i].markdown(
            f'<div class="metric-card">'
            f'<div class="metric-num" style="color:{color}">{cnt}</div>'
            f'<div class="metric-label">{cls}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )
    metric_cols[-2].markdown(
        f'<div class="metric-card">'
        f'<div class="metric-num" style="color:#4FC3F7">{len(detections)}</div>'
        f'<div class="metric-label">Total Objects</div>'
        f'</div>', unsafe_allow_html=True,
    )
    metric_cols[-1].markdown(
        f'<div class="metric-card">'
        f'<div class="metric-num" style="color:#CE93D8">{elapsed_ms:.0f} ms</div>'
        f'<div class="metric-label">Inference</div>'
        f'</div>', unsafe_allow_html=True,
    )

    # ── Detection table ───────────────────────────────────────────────────────
    if detections:
        st.divider()
        st.markdown("### 🗂️ All Detections")
        det_data = [
            {
                "Class":             d["class"],
                "Confidence":        f'{d["confidence"]*100:.1f}%',
                "BBox (x1,y1,x2,y2)": str(d["bbox"]),
            }
            for d in sorted(detections, key=lambda x: -x["confidence"])
        ]
        st.dataframe(
            det_data,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Class":      st.column_config.TextColumn(width="medium"),
                "Confidence": st.column_config.TextColumn(width="small"),
            },
        )

        buf = io.BytesIO()
        annotated.save(buf, format="JPEG", quality=95)
        st.download_button(
            label="💾 Download Annotated Image",
            data=buf.getvalue(),
            file_name=f"detected_{uploaded.name}",
            mime="image/jpeg",
        )
    else:
        st.warning(
            "Không tìm thấy object nào. Thử giảm Confidence threshold trong sidebar.",
            icon="⚠️",
        )