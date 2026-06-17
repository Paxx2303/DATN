"""Update slide number text from old/24 format to new N/17 format."""
import os, re

SLIDES_DIR = r'C:\Using\DATN\pptx_unpacked\ppt\slides'

# Maps slide file -> (old_number, new_number)
# Presentation.xml order determines new slide number
SLIDE_MAP = {
    'slide1.xml':  (1,  1),
    'slide2.xml':  (2,  2),
    'slide3.xml':  (3,  3),
    'slide5.xml':  (5,  4),
    'slide7.xml':  (7,  5),
    'slide8.xml':  (8,  6),
    'slide9.xml':  (9,  7),
    'slide10.xml': (10, 8),
    'slide12.xml': (12, 9),
    'slide13.xml': (13, 10),
    'slide14.xml': (14, 11),
    'slide15.xml': (15, 12),
    'slide19.xml': (19, 13),
    'slide20.xml': (20, 14),
    'slide22.xml': (22, 15),
    'slide23.xml': (23, 16),
    'slide24.xml': (24, 17),
}

for slide_file, (old_n, new_n) in SLIDE_MAP.items():
    path = os.path.join(SLIDES_DIR, slide_file)
    if not os.path.exists(path):
        print(f'MISSING: {slide_file}')
        continue
    with open(path, 'r', encoding='utf-8') as f:
        xml = f.read()

    # Replace old slide number patterns
    old_patterns = [
        f'{old_n}/24',
        f'{old_n} / 24',
    ]
    new_text = f'{new_n}/17'
    changed = False
    for pat in old_patterns:
        if pat in xml:
            xml = xml.replace(pat, new_text)
            changed = True

    if changed:
        with open(path, 'w', encoding='utf-8') as f:
            f.write(xml)
        print(f'{slide_file}: {old_n}/24 -> {new_n}/17')
    else:
        print(f'{slide_file}: no number found (check manually)')
