import re

with open(r'C:\Using\DATN\create_pptx_v2.py', encoding='utf-8') as f:
    src = f.read()

orig = src

# 1. Fix add_table defaults (signature line)
src = src.replace('fs=Pt(24), hfs=Pt(24)):', 'fs=Pt(13), hfs=Pt(14)):')

# 2. Fix cell_set inner function default
src = src.replace(
    'def cell_set(cell, text, bold=False, bg=None, fg=WHITE, sz=Pt(24), al=PP_ALIGN.LEFT, it=False):',
    'def cell_set(cell, text, bold=False, bg=None, fg=WHITE, sz=Pt(13), al=PP_ALIGN.LEFT, it=False):'
)

# 3. Fix fs= in add_table call sites
src = src.replace('fs=Pt(24))', 'fs=Pt(13))')
src = src.replace('fs=Pt(19))', 'fs=Pt(13))')

# 4. Fix Consolas code blocks (tracking algo + heatmap code on dark bg)
src = src.replace(
    "size=Pt(19), color=RGBColor(0x90, 0xFF, 0x90), font='Consolas')",
    "size=Pt(11), color=RGBColor(0x90, 0xFF, 0x90), font='Consolas')"
)
# Speed formula box
src = src.replace(
    "size=Pt(24), color=NAVY, font='Consolas')",
    "size=Pt(12), color=NAVY, font='Consolas')"
)
# LoS condition pill
src = src.replace(
    "size=Pt(19), bold=True, color=col, align=PP_ALIGN.CENTER, font='Consolas')",
    "size=Pt(13), bold=True, color=col, align=PP_ALIGN.CENTER, font='Consolas')"
)

print(f'Characters changed: {sum(1 for a,b in zip(orig,src) if a!=b)}')
for pattern in ['fs=Pt(24)', 'fs=Pt(19)', 'hfs=Pt(24)', 'sz=Pt(24)']:
    print(f'  {pattern}: {src.count(pattern)} remaining')

print()
print('Consolas lines after fix:')
for i, line in enumerate(src.splitlines()):
    if 'Consolas' in line:
        print(f'  L{i+1}: {line.strip()[:90]}')

with open(r'C:\Using\DATN\create_pptx_v2.py', 'w', encoding='utf-8') as f:
    f.write(src)
print('Saved.')
