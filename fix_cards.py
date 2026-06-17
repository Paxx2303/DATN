# -*- coding: utf-8 -*-
"""Fix colored card headers where 2-line titles overflow out of the colored bar"""

with open(r'C:\Using\DATN\create_pptx_v2.py', encoding='utf-8') as f:
    src = f.read()

orig = src
fixes = []

def rep(old, new, tag):
    global src
    if old not in src:
        print(f"  NOT FOUND: {tag}")
        return
    src = src.replace(old, new, 1)
    fixes.append(tag)

# ════════════════════════════════════════════════════════════
# SLIDE 23 — Future cards: header bar 0.52" too small for 2-line title at Pt(17)
# "Thu thập\ndữ liệu VN" etc: 2 × 17/72 × 1.2 = 0.57" needed, bar only 0.52"
# Fix: bar → 0.72", title box → 0.65", desc start → 3.97", desc h → 2.15"
rep(
    """    add_rect(sl, x, CONTENT_Y + Inches(3.2), Inches(3.07), Inches(3.0), fill=LGRAY)
    add_rect(sl, x, CONTENT_Y + Inches(3.2), Inches(3.07), Inches(0.52), fill=col)
    add_text(sl, ttl, x + Inches(0.1), CONTENT_Y + Inches(3.27), Inches(2.87), Inches(0.44),
             size=Pt(17), bold=True, color=WHITE)
    add_text(sl, dsc, x + Inches(0.1), CONTENT_Y + Inches(3.78), Inches(2.87), Inches(2.3),
             size=Pt(19), color=DGRAY, wrap=True)""",
    """    add_rect(sl, x, CONTENT_Y + Inches(3.2), Inches(3.07), Inches(2.97), fill=LGRAY)
    add_rect(sl, x, CONTENT_Y + Inches(3.2), Inches(3.07), Inches(0.72), fill=col)
    add_text(sl, ttl, x + Inches(0.1), CONTENT_Y + Inches(3.28), Inches(2.87), Inches(0.65),
             size=Pt(17), bold=True, color=WHITE)
    add_text(sl, dsc, x + Inches(0.1), CONTENT_Y + Inches(3.97), Inches(2.87), Inches(2.1),
             size=Pt(17), color=DGRAY, wrap=True)""",
    "S23 future card header 0.52->0.72, title box 0.44->0.65, desc 19->17"
)

# ════════════════════════════════════════════════════════════
# SLIDE 7 — Component boxes: "BACKBONE\nC3k2" 2-line at Pt(17) in 0.52" textbox
# Bar is 0.62" so bar is OK, but textbox 0.52" clips 2nd line (needs 0.57")
rep(
    """    add_text(sl, ttl, x + Inches(0.1), CONTENT_Y + Inches(3.8), Inches(3.9), Inches(0.52),
             size=Pt(17), bold=True, color=WHITE)""",
    """    add_text(sl, ttl, x + Inches(0.1), CONTENT_Y + Inches(3.8), Inches(3.9), Inches(0.60),
             size=Pt(17), bold=True, color=WHITE)""",
    "S7 comp title box 0.52->0.60 for 2-line titles"
)

# ════════════════════════════════════════════════════════════
# SLIDE 3 — Goal card descriptions: "Nâng cao phát hiện đối tượng\nnhỏ..." at Pt(24)
# in 2.8" wide box → wraps to 3-4 lines, overflows 1.5" box height
rep(
    """    add_text(sl, dsc,  x + Inches(1.2), CONTENT_Y + Inches(0.85), Inches(2.8), Inches(1.5),
             size=Pt(24), color=RGBColor(0xDD, 0xDD, 0xFF))""",
    """    add_text(sl, dsc,  x + Inches(1.2), CONTENT_Y + Inches(0.85), Inches(2.8), Inches(1.5),
             size=Pt(19), color=RGBColor(0xDD, 0xDD, 0xFF), wrap=True)""",
    "S3 goal desc 24->19 to prevent wrap overflow in 2.8\" width"
)

# ════════════════════════════════════════════════════════════
# SLIDE 4 — Benefit card descriptions: Pt(24) in 0.95" box, 2-line text
# "Giảm ~75% số lượng\nthiết bị lắp đặt" = 2 lines at 24pt = 0.8" < 0.95". Tight.
# BUT card title line "💰 Tiết kiệm chi phí" at 19pt in 0.48" is fine.
# The description is on colored bg so safe if slight overflow (stays visible).
# Change to Pt(19) for comfort.
rep(
    """    add_text(sl, dsc, x + Inches(0.12), CONTENT_Y + Inches(4.45), Inches(2.85), Inches(0.95),
             size=Pt(24), color=RGBColor(0xDD, 0xDD, 0xFF), wrap=True)""",
    """    add_text(sl, dsc, x + Inches(0.12), CONTENT_Y + Inches(4.45), Inches(2.85), Inches(0.95),
             size=Pt(19), color=RGBColor(0xDD, 0xDD, 0xFF), wrap=True)""",
    "S4 benefit desc 24->19"
)

# ════════════════════════════════════════════════════════════
# SLIDE 9 — Pipeline boxes: "Đọc ảnh\n+ nhãn" at Pt(24) in 0.85" — 2×0.4=0.8" OK but tight
# Also the description text alignment: BLUE boxes white text OK, LGRAY boxes navy text OK
# No fix needed — 0.85" > 0.8" needed

# ════════════════════════════════════════════════════════════
# SLIDE 13 — Layer labels at Pt(19) in 0.42" box — single-line OK
# BUT layer descriptions at Pt(17) in 0.78" box — some are VERY long
# "Flask App Factory: create_app(): Config → DB → Blueprints..." = 3+ lines at Pt(17) = 0.85"+ > 0.78"
# Fix: increase description box height to 0.82" and move arrow down
rep(
    """    add_text(sl, dsc, Inches(2.68), y + Inches(0.05), Inches(5.3), Inches(0.78),
             size=Pt(17), color=WHITE, wrap=True)
    if i < 4:
        add_text(sl, "▼", Inches(4.0), y + Inches(0.88), Inches(0.5), Inches(0.12),
                 size=Pt(19), color=MGRAY, align=PP_ALIGN.CENTER)""",
    """    add_text(sl, dsc, Inches(2.68), y + Inches(0.05), Inches(5.3), Inches(0.82),
             size=Pt(14), color=WHITE, wrap=True)
    if i < 4:
        add_text(sl, "▼", Inches(4.0), y + Inches(0.88), Inches(0.5), Inches(0.12),
                 size=Pt(17), color=MGRAY, align=PP_ALIGN.CENTER)""",
    "S13 layer desc 17->14, h 0.78->0.82 for long text"
)

# ════════════════════════════════════════════════════════════
# SLIDE 10 — Hyperparameter table right panel: technique descriptions
# "Ưu tiên lớp thiểu số\nBus, Truck khi augment" — already changed to Pt(17)
# at 0.62" box: 2 × 17/72 × 1.2 = 0.567" < 0.62". OK.

# ════════════════════════════════════════════════════════════
# SLIDE 15 — Module row: description box h increased to 0.48" and size to Pt(14)
# module row height is 1.0", description occupies 0.48" from y+0.52" to y+1.0". OK.

# ════════════════════════════════════════════════════════════
# SLIDE 17 — LoS card body: "Tắc nghẽn nghiêm trọng\nCần can thiệp ngay" at Pt(24) in 1.72"
# 2 lines × 0.4" = 0.8" < 1.72". Fine.
# LoS level title "FREE\nThông thoáng" at Pt(24) in 1.05". Fine.

# ════════════════════════════════════════════════════════════
# SLIDE 6 — Step descriptions with \n at Pt(24): "Biến đổi bán kính phi tuyến:\nr' = ..."
# In box 4.75" wide × 1.1" tall. At 24pt: 2 explicit lines but "r' = r^(1 + strength)"
# wraps? 22 chars × 0.2 = 4.4" < 4.75". OK. 2 lines × 0.4" = 0.8" < 1.1". OK.

# ════════════════════════════════════════════════════════════
print(f"Applied {len(fixes)} fixes:")
for f in fixes:
    print(f"  OK  {f}")

with open(r'C:\Using\DATN\create_pptx_v2.py', 'w', encoding='utf-8') as f:
    f.write(src)
print(f"\nSaved. {sum(1 for a,b in zip(orig,src) if a!=b)} chars changed.")
