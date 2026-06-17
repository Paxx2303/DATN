# -*- coding: utf-8 -*-
"""Fix all text overflow / clipping issues in create_pptx_v2.py"""

with open(r'C:\Using\DATN\create_pptx_v2.py', encoding='utf-8') as f:
    src = f.read()

orig = src
changes = []

def rep(old, new, tag=""):
    global src
    if old not in src:
        print(f"  NOT FOUND: {tag!r}")
        return False
    src = src.replace(old, new, 1)
    changes.append(tag)
    return True

# ─────────────────────────────────────────────
# SLIDE 1 — university name in header bar: 24pt OK, but add_text default is now Pt(24) so fine.
# No change needed for slide 1 fonts.

# ─────────────────────────────────────────────
# SLIDE 2 — bullet lists too long for 24pt in constrained boxes
# 3 bullets (Thực Trạng): h=1.65", 24pt per long line wraps → overflow
rep(
    """add_lines(sl, [
    ("• 7,8 triệu ô tô & 73 triệu xe máy đang lưu hành (Tổng cục Thống kê, 2024)", False, DGRAY, Pt(24)),
    ("• Năm 2023: hơn 10.000 vụ tai nạn giao thông nghiêm trọng", False, DGRAY, Pt(24)),
    ("• Camera CCTV truyền thống: giám sát thủ công — không phân tích tự động", False, DGRAY, Pt(24)),
], Inches(0.38), CONTENT_Y + Inches(0.52), Inches(7.5), Inches(1.65))""",
    """add_lines(sl, [
    ("• 7,8 triệu ô tô & 73 triệu xe máy đang lưu hành (Tổng cục Thống kê, 2024)", False, DGRAY, Pt(19)),
    ("• Năm 2023: hơn 10.000 vụ tai nạn giao thông nghiêm trọng", False, DGRAY, Pt(19)),
    ("• Camera CCTV truyền thống: giám sát thủ công — không phân tích tự động", False, DGRAY, Pt(19)),
], Inches(0.38), CONTENT_Y + Inches(0.52), Inches(7.5), Inches(1.65))""",
    "S2 thực trạng bullets 24→19"
)

rep(
    """add_lines(sl, [
    ("• Góc nhìn 180°–220° — một camera bao phủ toàn bộ ngã tư", True, RGBColor(0x8B, 0x45, 0x13), Pt(24)),
    ("• Tiết kiệm chi phí: thay thế 4 camera thường bằng 1 camera fisheye", False, DGRAY, Pt(24)),
    ("• Nhưng gây barrel distortion → AI thông thường không áp dụng trực tiếp", False, DGRAY, Pt(24)),
], Inches(0.38), CONTENT_Y + Inches(2.95), Inches(7.5), Inches(1.4))""",
    """add_lines(sl, [
    ("• Góc nhìn 180°–220° — một camera bao phủ toàn bộ ngã tư", True, RGBColor(0x8B, 0x45, 0x13), Pt(19)),
    ("• Tiết kiệm chi phí: thay thế 4 camera thường bằng 1 camera fisheye", False, DGRAY, Pt(19)),
    ("• Nhưng gây barrel distortion → AI thông thường không áp dụng trực tiếp", False, DGRAY, Pt(19)),
], Inches(0.38), CONTENT_Y + Inches(2.95), Inches(7.5), Inches(1.4))""",
    "S2 fisheye bullets 24→19"
)

# Slide 2: challenge boxes bottom goes below orange bar: CONTENT_Y+4.63+1.75 = 7.38" > 7.25"
# Fix: reduce h from 1.75 to 1.65, description from 0.88 to 0.78
rep(
    """    add_rect(sl, x, CONTENT_Y + Inches(4.63), Inches(3.1), Inches(1.75), fill=LGRAY)
    add_rect(sl, x, CONTENT_Y + Inches(4.63), Inches(3.1), Inches(0.06), fill=BLUE)
    add_text(sl, ttl, x + Inches(0.1), CONTENT_Y + Inches(4.72), Inches(2.9), Inches(0.65),
             size=Pt(19), bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    add_text(sl, dsc, x + Inches(0.1), CONTENT_Y + Inches(5.38), Inches(2.9), Inches(0.88),
             size=Pt(17), color=DGRAY, wrap=True)""",
    """    add_rect(sl, x, CONTENT_Y + Inches(4.55), Inches(3.1), Inches(1.62), fill=LGRAY)
    add_rect(sl, x, CONTENT_Y + Inches(4.55), Inches(3.1), Inches(0.06), fill=BLUE)
    add_text(sl, ttl, x + Inches(0.1), CONTENT_Y + Inches(4.63), Inches(2.9), Inches(0.55),
             size=Pt(17), bold=True, color=NAVY, align=PP_ALIGN.CENTER)
    add_text(sl, dsc, x + Inches(0.1), CONTENT_Y + Inches(5.22), Inches(2.9), Inches(0.82),
             size=Pt(14), color=DGRAY, wrap=True)""",
    "S2 challenge boxes moved up, sizes reduced"
)

# ─────────────────────────────────────────────
# SLIDE 5 — effect cards bottom at 7.33" > 7.25" orange bar
# Move y from 4.28 to 4.18, reduce h from 2.05 to 1.95
rep(
    """    add_rect(sl, x, CONTENT_Y + Inches(4.28), Inches(3.07), Inches(2.05), fill=LGRAY)
    add_text(sl, ttl, x + Inches(0.1), CONTENT_Y + Inches(4.36), Inches(2.87), Inches(0.45),
             size=Pt(19), bold=True, color=NAVY)
    add_text(sl, dsc, x + Inches(0.1), CONTENT_Y + Inches(4.85), Inches(2.87), Inches(1.35),
             size=Pt(24), color=DGRAY, wrap=True)""",
    """    add_rect(sl, x, CONTENT_Y + Inches(4.15), Inches(3.07), Inches(1.95), fill=LGRAY)
    add_text(sl, ttl, x + Inches(0.1), CONTENT_Y + Inches(4.23), Inches(2.87), Inches(0.42),
             size=Pt(19), bold=True, color=NAVY)
    add_text(sl, dsc, x + Inches(0.1), CONTENT_Y + Inches(4.7), Inches(2.87), Inches(1.25),
             size=Pt(19), color=DGRAY, wrap=True)""",
    "S5 effect cards moved up, desc 24→19"
)

# ─────────────────────────────────────────────
# SLIDE 6 — bbox steps: wrapping Pt(24) in h=0.48" boxes
rep(
    """for i, s in enumerate(bbox_steps):
    add_text(sl, s, Inches(6.62), CONTENT_Y + Inches(0.58 + i * 0.52), Inches(6.35), Inches(0.48),
             size=Pt(24), color=DGRAY, wrap=True)""",
    """for i, s in enumerate(bbox_steps):
    add_text(sl, s, Inches(6.62), CONTENT_Y + Inches(0.58 + i * 0.6), Inches(6.35), Inches(0.55),
             size=Pt(17), color=DGRAY, wrap=True)""",
    "S6 bbox steps 24→17, spacing 0.52→0.60, h 0.48→0.55"
)

# Slide 6 bottom labels: h=0.32" clips Pt(24) (needs 0.4"+)
rep(
    """add_text(sl, "→ Tương đồng camera equidistant thực tế",
         Inches(0.38), CONTENT_Y + Inches(4.42), Inches(5.85), Inches(0.32),
         size=Pt(24), color=DGRAY, italic=True)
add_text(sl, "4 profile: standard · extreme · subtle · traffic_camera",
         Inches(0.38), CONTENT_Y + Inches(4.8), Inches(5.85), Inches(0.32),
         size=Pt(24), bold=True, color=BLUE)
add_text(sl, "Hiệu năng: ~50–100ms/frame ảnh 1080p (CPU)",
         Inches(0.38), CONTENT_Y + Inches(5.18), Inches(5.85), Inches(0.32),
         size=Pt(24), color=DGRAY, italic=True)""",
    """add_text(sl, "→ Tương đồng camera equidistant thực tế",
         Inches(0.38), CONTENT_Y + Inches(4.42), Inches(5.85), Inches(0.38),
         size=Pt(17), color=DGRAY, italic=True)
add_text(sl, "4 profile: standard · extreme · subtle · traffic_camera",
         Inches(0.38), CONTENT_Y + Inches(4.83), Inches(5.85), Inches(0.38),
         size=Pt(17), bold=True, color=BLUE)
add_text(sl, "Hiệu năng: ~50–100ms/frame ảnh 1080p (CPU)",
         Inches(0.38), CONTENT_Y + Inches(5.24), Inches(5.85), Inches(0.38),
         size=Pt(17), color=DGRAY, italic=True)""",
    "S6 bottom labels 24→17, h 0.32→0.38"
)

# ─────────────────────────────────────────────
# SLIDE 7 — stat label box h=0.3" clips Pt(24)
rep(
    """    add_text(sl, l, x + Inches(0.1), CONTENT_Y + Inches(0.63), Inches(2.87), Inches(0.3),
             size=Pt(24), color=RGBColor(0xCC, 0xCC, 0xFF), align=PP_ALIGN.CENTER)""",
    """    add_text(sl, l, x + Inches(0.1), CONTENT_Y + Inches(0.62), Inches(2.87), Inches(0.35),
             size=Pt(17), color=RGBColor(0xCC, 0xCC, 0xFF), align=PP_ALIGN.CENTER)""",
    "S7 stat label 24→17, h 0.3→0.35"
)

# ─────────────────────────────────────────────
# SLIDE 8 — SAHI steps: wrapping Pt(24) in h=0.62" boxes
rep(
    """for i, s in enumerate(sahi_steps):
    y = CONTENT_Y + Inches(1.22 + i * 0.7)
    add_rect(sl, Inches(0.38), y, Inches(5.4), Inches(0.62), fill=WHITE)
    add_rect(sl, Inches(0.38), y, Inches(0.06), Inches(0.62), fill=BLUE)
    add_text(sl, s, Inches(0.52), y + Inches(0.08), Inches(5.1), Inches(0.5),
             size=Pt(24), color=DGRAY, wrap=True)""",
    """for i, s in enumerate(sahi_steps):
    y = CONTENT_Y + Inches(1.22 + i * 0.72)
    add_rect(sl, Inches(0.38), y, Inches(5.4), Inches(0.64), fill=WHITE)
    add_rect(sl, Inches(0.38), y, Inches(0.06), Inches(0.64), fill=BLUE)
    add_text(sl, s, Inches(0.52), y + Inches(0.08), Inches(5.1), Inches(0.52),
             size=Pt(17), color=DGRAY, wrap=True)""",
    "S8 SAHI steps 24→17"
)

# Slide 8 right panel bullets: potentially overflowing 2.85" box at Pt(24)
rep(
    """add_lines(sl, [
    ("Lợi ích trong bài toán fisheye:", True, NAVY, Pt(19)),
    ("• Mỗi lát ảnh có biến dạng cục bộ ít hơn → model dễ học hơn", False, DGRAY, Pt(24)),
    ("• Đối tượng nhỏ ở biên xuất hiện tương đối lớn hơn trong lát", False, DGRAY, Pt(24)),
    ("", False, DGRAY, Pt(11)),
    ("Đánh đổi tốc độ:", True, NAVY, Pt(19)),
    ("• Inference: 1.8–2.5 giây/ảnh (6–8× chậm hơn standard)", False, DGRAY, Pt(24)),
    ("• Phù hợp: phân tích offline, snapshot định kỳ 2–3s/lần", False, DGRAY, Pt(24)),
], Inches(6.18), CONTENT_Y + Inches(2.82), Inches(6.7), Inches(2.85))""",
    """add_lines(sl, [
    ("Lợi ích trong bài toán fisheye:", True, NAVY, Pt(19)),
    ("• Mỗi lát ảnh có biến dạng cục bộ ít hơn → model dễ học hơn", False, DGRAY, Pt(19)),
    ("• Đối tượng nhỏ ở biên xuất hiện tương đối lớn hơn trong lát", False, DGRAY, Pt(19)),
    ("", False, DGRAY, Pt(11)),
    ("Đánh đổi tốc độ:", True, NAVY, Pt(19)),
    ("• Inference: 1.8–2.5 giây/ảnh (6–8× chậm hơn standard)", False, DGRAY, Pt(19)),
    ("• Phù hợp: phân tích offline, snapshot định kỳ 2–3s/lần", False, DGRAY, Pt(19)),
], Inches(6.18), CONTENT_Y + Inches(2.82), Inches(6.7), Inches(2.85))""",
    "S8 right bullets 24→19"
)

# ─────────────────────────────────────────────
# SLIDE 9 — combined summary bar: long text wraps in h=0.45"
rep(
    """add_text(sl, "Dataset kết hợp:  Train 11.296 ảnh · 406.355 nhãn (TB 35,97 nhãn/ảnh)  |  Val 1.768 ảnh · ~58.000 nhãn",
         Inches(0.4), CONTENT_Y + Inches(5.05), Inches(7.6), Inches(0.45),
         size=Pt(19), bold=True, color=GREEN)""",
    """add_text(sl, "Dataset kết hợp:  Train 11.296 ảnh · 406.355 nhãn (TB 35,97 nhãn/ảnh)  |  Val 1.768 ảnh · ~58.000 nhãn",
         Inches(0.4), CONTENT_Y + Inches(5.05), Inches(7.6), Inches(0.55),
         size=Pt(17), bold=True, color=GREEN)""",
    "S9 combined summary 19→17, h 0.45→0.55"
)

# ─────────────────────────────────────────────
# SLIDE 10 — environment bar: very long at Pt(24) in h=0.4"
rep(
    """add_text(sl, "Môi trường: Kaggle Notebooks  ·  GPU Tesla P100-PCIE-16GB  ·  17.1 GB VRAM  ·  RAM 25 GB  ·  CUDA 12.1  ·  PyTorch 2.2",
         Inches(0.42), CONTENT_Y + Inches(0.07), Inches(12.4), Inches(0.4),
         size=Pt(24), color=NAVY, align=PP_ALIGN.CENTER)""",
    """add_text(sl, "Môi trường: Kaggle Notebooks  ·  GPU Tesla P100-PCIE-16GB  ·  17.1 GB VRAM  ·  RAM 25 GB  ·  CUDA 12.1  ·  PyTorch 2.2",
         Inches(0.42), CONTENT_Y + Inches(0.07), Inches(12.4), Inches(0.42),
         size=Pt(17), color=NAVY, align=PP_ALIGN.CENTER)""",
    "S10 env bar 24→17"
)

# Slide 10 technique card descriptions: 2-line text in h=0.62"
rep(
    """    add_text(sl, d, Inches(8.98), y + Inches(0.56), Inches(3.8), Inches(0.62),
             size=Pt(24), color=DGRAY, wrap=True)""",
    """    add_text(sl, d, Inches(8.98), y + Inches(0.56), Inches(3.8), Inches(0.62),
             size=Pt(17), color=DGRAY, wrap=True)""",
    "S10 technique desc 24→17"
)

# ─────────────────────────────────────────────
# SLIDE 11 — highlight labels h=0.38" clips Pt(24)
rep(
    """    add_text(sl, lbl, x + Inches(0.1), CONTENT_Y + Inches(5.1), Inches(2.87), Inches(0.38),
             size=Pt(24), color=WHITE, align=PP_ALIGN.CENTER)""",
    """    add_text(sl, lbl, x + Inches(0.1), CONTENT_Y + Inches(5.1), Inches(2.87), Inches(0.42),
             size=Pt(17), color=WHITE, align=PP_ALIGN.CENTER)""",
    "S11 highlight label 24→17, h 0.38→0.42"
)

# ─────────────────────────────────────────────
# SLIDE 12 — improvement metric label h=0.35" clips Pt(24)
rep(
    """    add_text(sl, m,    x + Inches(0.1), CONTENT_Y + Inches(2.5), Inches(2.87), Inches(0.35),
             size=Pt(24), bold=True, color=NAVY, align=PP_ALIGN.CENTER)""",
    """    add_text(sl, m,    x + Inches(0.1), CONTENT_Y + Inches(2.5), Inches(2.87), Inches(0.42),
             size=Pt(17), bold=True, color=NAVY, align=PP_ALIGN.CENTER)""",
    "S12 metric label 24→17, h 0.35→0.42"
)

# ─────────────────────────────────────────────
# SLIDE 13 — tech stack bar: very long at Pt(24) in h=0.38"
rep(
    """add_text(sl, "Flask 3.x · Python 3.10 · YOLOv11 · OpenCV · EasyOCR · SQLite/PostgreSQL · Docker · GCP",
         Inches(0.28), CONTENT_Y + Inches(4.98), Inches(12.77), Inches(0.38),
         size=Pt(24), bold=True, color=NAVY, align=PP_ALIGN.CENTER)""",
    """add_text(sl, "Flask 3.x · Python 3.10 · YOLOv11 · OpenCV · EasyOCR · SQLite/PostgreSQL · Docker · GCP",
         Inches(0.28), CONTENT_Y + Inches(4.98), Inches(12.77), Inches(0.4),
         size=Pt(17), bold=True, color=NAVY, align=PP_ALIGN.CENTER)""",
    "S13 tech stack 24→17"
)

# ─────────────────────────────────────────────
# SLIDE 14 — flow box labels: 2-line Pt(24) in h=0.72" (needs 0.8")
rep(
    """    add_text(sl, lbl, x + Inches(0.07), CONTENT_Y + Inches(1.22), Inches(1.86), Inches(0.72),
             size=Pt(24), bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(sl, sub, x + Inches(0.07), CONTENT_Y + Inches(1.94), Inches(1.86), Inches(0.28),
             size=Pt(24), color=MGRAY, align=PP_ALIGN.CENTER)""",
    """    add_text(sl, lbl, x + Inches(0.07), CONTENT_Y + Inches(1.22), Inches(1.86), Inches(0.75),
             size=Pt(19), bold=True, color=WHITE, align=PP_ALIGN.CENTER)
    add_text(sl, sub, x + Inches(0.07), CONTENT_Y + Inches(1.97), Inches(1.86), Inches(0.32),
             size=Pt(14), color=MGRAY, align=PP_ALIGN.CENTER)""",
    "S14 flow labels 24→19/14"
)

# Slide 14 worker steps: Pt(24) in h=0.32" boxes
rep(
    """    add_text(sl, s, x + Inches(0.4), y, Inches(3.72), Inches(0.32), size=Pt(24), color=DGRAY)""",
    """    add_text(sl, s, x + Inches(0.4), y, Inches(3.72), Inches(0.38), size=Pt(17), color=DGRAY)""",
    "S14 worker steps 24→17, h 0.32→0.38"
)

# ─────────────────────────────────────────────
# SLIDE 15 — module descriptions: wrapping Pt(17) in h=0.42"
rep(
    """    add_text(sl, dsc, Inches(1.28), y + Inches(0.52), Inches(6.5), Inches(0.42),
             size=Pt(17), color=DGRAY, wrap=True)""",
    """    add_text(sl, dsc, Inches(1.28), y + Inches(0.52), Inches(6.5), Inches(0.48),
             size=Pt(14), color=DGRAY, wrap=True)""",
    "S15 module desc 17→14, h 0.42→0.48"
)

# ─────────────────────────────────────────────
# SLIDE 16 — speed violation warning: wrapping Pt(24) in h=0.55"
rep(
    """add_text(sl, "Cảnh báo vi phạm: Tốc độ > ngưỡng trong ≥ 3 frame liên tiếp → lưu bản ghi vi phạm",
         Inches(6.55), CONTENT_Y + Inches(4.65), Inches(6.5), Inches(0.55),
         size=Pt(24), bold=True, color=NAVY, wrap=True)""",
    """add_text(sl, "Cảnh báo vi phạm: Tốc độ > ngưỡng trong ≥ 3 frame liên tiếp → lưu bản ghi vi phạm",
         Inches(6.55), CONTENT_Y + Inches(4.62), Inches(6.5), Inches(0.72),
         size=Pt(19), bold=True, color=NAVY, wrap=True)""",
    "S16 warning 24→19, h 0.55→0.72"
)

# ─────────────────────────────────────────────
# SLIDE 17 — method bar: very long Pt(24) in h=0.44"
rep(
    """add_text(sl, "Phương pháp: Phân tích mật độ trong ROI (tọa độ chuẩn hóa ∈ [0,1]²)   "
             "·   Trọng số: Motorbike 0.5 · Car 1.0 · Truck 2.0 · Bus 2.5 · Pedestrian 0.3",
         Inches(0.42), CONTENT_Y + Inches(0.1), Inches(12.4), Inches(0.44),
         size=Pt(24), bold=True, color=NAVY, align=PP_ALIGN.CENTER)""",
    """add_text(sl, "Phương pháp: Phân tích mật độ trong ROI (tọa độ chuẩn hóa ∈ [0,1]²)   "
             "·   Trọng số: Motorbike 0.5 · Car 1.0 · Truck 2.0 · Bus 2.5 · Pedestrian 0.3",
         Inches(0.42), CONTENT_Y + Inches(0.1), Inches(12.4), Inches(0.48),
         size=Pt(17), bold=True, color=NAVY, align=PP_ALIGN.CENTER)""",
    "S17 method bar 24→17"
)

# Slide 17 viz bar: long Pt(24) in h=0.42"
rep(
    """add_text(sl, "Visualization: Hình chữ nhật bán trong suốt theo màu  ·  Text: tên ROI, số xe/capacity, %  ·  Dashboard tổng hợp",
         Inches(0.42), CONTENT_Y + Inches(4.67), Inches(12.4), Inches(0.42),
         size=Pt(24), color=NAVY)""",
    """add_text(sl, "Visualization: Hình chữ nhật bán trong suốt theo màu  ·  Text: tên ROI, số xe/capacity, %  ·  Dashboard tổng hợp",
         Inches(0.42), CONTENT_Y + Inches(4.67), Inches(12.4), Inches(0.42),
         size=Pt(17), color=NAVY)""",
    "S17 viz bar 24→17"
)

# Slide 17 alert bar: Pt(24) in h=0.35"
rep(
    """add_text(sl, "Alert: SEVERE → Gửi webhook (không block pipeline chính)  ·  alert_manager async call",
         Inches(0.42), CONTENT_Y + Inches(5.28), Inches(12.4), Inches(0.35),
         size=Pt(24), bold=True, color=WHITE)""",
    """add_text(sl, "Alert: SEVERE → Gửi webhook (không block pipeline chính)  ·  alert_manager async call",
         Inches(0.42), CONTENT_Y + Inches(5.28), Inches(12.4), Inches(0.38),
         size=Pt(17), bold=True, color=WHITE)""",
    "S17 alert bar 24→17"
)

# ─────────────────────────────────────────────
# SLIDE 18 — ALPR steps: step text h=0.85", Pt(24) — some steps are 2-line
# Step ③ has explicit \n → 2 lines at 24pt = 0.8". Box h=0.85". Tight. Reduce to Pt(19).
rep(
    """    add_text(sl, s, Inches(7.2), y, Inches(5.7), Inches(0.85),
             size=Pt(24), color=DGRAY, wrap=True)""",
    """    add_text(sl, s, Inches(7.2), y, Inches(5.7), Inches(0.85),
             size=Pt(19), color=DGRAY, wrap=True)""",
    "S18 ALPR steps 24→19"
)

# Slide 18 dashboard bullets: 5 bullets at Pt(24) in h=2.85" — fine but reduce slightly
rep(
    """add_lines(sl, [(s, False, DGRAY, Pt(24)) for s in dashboard],
          Inches(0.38), CONTENT_Y + Inches(2.85), Inches(5.9), Inches(2.85))""",
    """add_lines(sl, [(s, False, DGRAY, Pt(19)) for s in dashboard],
          Inches(0.38), CONTENT_Y + Inches(2.85), Inches(5.9), Inches(2.85))""",
    "S18 dashboard bullets 24→19"
)

# ─────────────────────────────────────────────
# SLIDE 21 — NFR items: Pt(24) in 1.35" boxes — each item wraps in 2.25" width
# "✅ Chrome 90+, Firefox 88+, Edge 90+" → might be 2 lines at 24pt in 2.25"
# At 24pt, 35 chars × ~0.2 = 7" > 2.25" → wraps to 3-4 lines. Need Pt(17).
rep(
    """    add_text(sl, nfr, x + Inches(0.1), CONTENT_Y + Inches(4.25), Inches(2.25), Inches(1.35),
             size=Pt(24), bold=True, color=GREEN, wrap=True)""",
    """    add_text(sl, nfr, x + Inches(0.1), CONTENT_Y + Inches(4.25), Inches(2.25), Inches(1.35),
             size=Pt(17), bold=True, color=GREEN, wrap=True)""",
    "S21 NFR items 24→17"
)

# ─────────────────────────────────────────────
# SLIDE 22 — app results: Pt(24) with spacing=1.35 in h=2.2" — marginal
rep(
    """add_lines(sl, [(r, False, GREEN if "✅" in r else DGRAY, Pt(24)) for r in app_results],
          Inches(6.62), CONTENT_Y + Inches(0.62), Inches(6.35), Inches(2.2), spacing=1.35)""",
    """add_lines(sl, [(r, False, GREEN if "✅" in r else DGRAY, Pt(19)) for r in app_results],
          Inches(6.62), CONTENT_Y + Inches(0.62), Inches(6.35), Inches(2.2), spacing=1.35)""",
    "S22 app results 24→19"
)

# ─────────────────────────────────────────────
# SLIDE 23 — future cards: bottom at CONTENT_Y+3.2+3.17 = 7.37" > 7.25" orange bar
rep(
    """    add_rect(sl, x, CONTENT_Y + Inches(3.2), Inches(3.07), Inches(3.17), fill=LGRAY)
    add_rect(sl, x, CONTENT_Y + Inches(3.2), Inches(3.07), Inches(0.58), fill=col)
    add_text(sl, ttl, x + Inches(0.1), CONTENT_Y + Inches(3.28), Inches(2.87), Inches(0.48),
             size=Pt(17), bold=True, color=WHITE)
    add_text(sl, dsc, x + Inches(0.1), CONTENT_Y + Inches(3.85), Inches(2.87), Inches(2.38),
             size=Pt(24), color=DGRAY, wrap=True)""",
    """    add_rect(sl, x, CONTENT_Y + Inches(3.2), Inches(3.07), Inches(3.0), fill=LGRAY)
    add_rect(sl, x, CONTENT_Y + Inches(3.2), Inches(3.07), Inches(0.52), fill=col)
    add_text(sl, ttl, x + Inches(0.1), CONTENT_Y + Inches(3.27), Inches(2.87), Inches(0.44),
             size=Pt(17), bold=True, color=WHITE)
    add_text(sl, dsc, x + Inches(0.1), CONTENT_Y + Inches(3.78), Inches(2.87), Inches(2.3),
             size=Pt(19), color=DGRAY, wrap=True)""",
    "S23 future cards h 3.17→3.0, desc 24→19"
)

# ─────────────────────────────────────────────
# SLIDE 3 — goal card: description at Pt(24) in box (2.8 × 1.5) is fine but check
# "Trên bộ dữ liệu kết hợp\nFishEye8K + VisDrone2019" = 2 explicit lines. OK at 24pt in 1.5".
# No fix needed.

# SLIDE 4 — benefit card desc: "Giảm ~75%..." 2-line at Pt(24) in h=0.95". Tight (0.8" needed). OK.

# SLIDE 9 pipeline boxes: "Đọc ảnh\n+ nhãn" 2-line at 24pt in h=0.85". OK (0.8").

# ─────────────────────────────────────────────
print(f"\nApplied {len(changes)} fixes:")
for c in changes:
    print(f"  ✓ {c}")

not_found = [tag for tag in [] if tag not in changes]

with open(r'C:\Using\DATN\create_pptx_v2.py', 'w', encoding='utf-8') as f:
    f.write(src)
print(f"\nSaved. Changed {sum(1 for a,b in zip(orig,src) if a!=b)} chars.")
