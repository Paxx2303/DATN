# -*- coding: utf-8 -*-
"""Scan for multi-line titles in colored bars with too-small heights"""
import re

with open(r'C:\Using\DATN\create_pptx_v2.py', encoding='utf-8') as f:
    src = f.read()
    lines = src.splitlines()

# Find slide section markers
slide_num = 0
current_slide = 0
for i, line in enumerate(lines):
    if '# SLIDE' in line:
        m = re.search(r'SLIDE (\d+)', line)
        if m:
            current_slide = int(m.group(1))

# Find all add_text calls with \n in the text arg
print("=== add_text calls with \\n in text ===")
for i, line in enumerate(lines):
    if 'add_text(' in line and '\\n' in line:
        # Find the h=Inches(...) at end of the line (last Inches value)
        h_match = list(re.finditer(r'Inches\(([\d.]+)\)', line))
        if h_match:
            h = float(h_match[-1].group(1))
            # Find size=Pt(x)
            sz_match = re.search(r'size=Pt\((\d+)\)', line)
            sz = int(sz_match.group(1)) if sz_match else 0
            # Calculate min height needed: 2 lines * pt/72 * 1.2
            needed = 2 * sz / 72 * 1.2
            status = "OVERFLOW" if h < needed else "ok"
            print(f"  L{i+1} [{status}] h={h:.2f}\" sz={sz}pt need={needed:.2f}\"  {line.strip()[:70]}")

print()
print("=== Cards with colored header bars (add_rect then add_text WHITE) ===")
# Look for the specific pattern: small colored bar + title text
for i in range(len(lines)-3):
    line = lines[i]
    if 'add_rect' in line and ('fill=col' in line or 'fill=NAVY' in line or 'fill=BLUE' in line or 'fill=ORANGE' in line or 'fill=RED' in line or 'fill=GREEN' in line):
        # Get the height of this rect
        h_match = list(re.finditer(r'Inches\(([\d.]+)\)', line))
        if len(h_match) >= 4:
            rect_h = float(h_match[3].group(1))  # 4th Inches() is usually height
            # Check if next few lines have text with \n
            for j in range(1, 5):
                if i+j < len(lines):
                    next_line = lines[i+j]
                    if 'add_text' in next_line and '\\n' in next_line:
                        sz_match = re.search(r'size=Pt\((\d+)\)', next_line)
                        sz = int(sz_match.group(1)) if sz_match else 0
                        needed = 2 * sz / 72 * 1.2
                        status = "BAR TOO SMALL" if rect_h < needed else "ok"
                        print(f"  L{i+1} bar h={rect_h:.2f}\" | L{i+1+j} [{status}] sz={sz}pt need={needed:.2f}\"")
                        print(f"    bar:  {line.strip()[:65]}")
                        print(f"    text: {next_line.strip()[:65]}")
