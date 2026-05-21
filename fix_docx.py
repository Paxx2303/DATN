import sys, io, copy, shutil
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'

def get_texts(elem):
    return ''.join(r.text for r in elem.findall(f'.//{{{NS}}}t') if r.text)

# Backup
shutil.copy('e:/test/DATN/YOLOv11_BaoCao_TiengViet_Fixed.docx',
            'e:/test/DATN/YOLOv11_BaoCao_TiengViet_Fixed_bak2.docx')
print('Backed up to YOLOv11_BaoCao_TiengViet_Fixed_bak2.docx')

fixed_doc = Document('e:/test/DATN/YOLOv11_BaoCao_TiengViet_Fixed.docx')
source_doc = Document('e:/test/DATN/BaoCaoTTTN_NguyenQuocNam_221220938 (2).docx')

fixed_body = fixed_doc.element.body
source_body = source_doc.element.body

# ── Step 1: Delete page 1 of Fixed.docx (children 0-35)
# Page 1 = everything before "LỜI CẢM ƠN" (body child 36)
fixed_children = list(fixed_body)
loi_cam_on_idx = None
for i, child in enumerate(fixed_children):
    if get_texts(child).strip() == 'LỜI CẢM ƠN':
        loi_cam_on_idx = i
        break

print(f'LỜI CẢM ƠN found at body child {loi_cam_on_idx}')
# Delete children 0 to loi_cam_on_idx-1 (everything before LỜI CẢM ƠN)
for child in fixed_children[:loi_cam_on_idx]:
    fixed_body.remove(child)

# ── Step 2: Delete page 3 (MỤC LỤC heading + TOC field paragraph)
fixed_children = list(fixed_body)
muc_luc_idx = None
for i, child in enumerate(fixed_children):
    if get_texts(child).strip() == 'MỤC LỤC':
        muc_luc_idx = i
        break

print(f'MỤC LỤC found at body child {muc_luc_idx} (after step 1 deletion)')
if muc_luc_idx is not None:
    # Delete MỤC LỤC heading
    fixed_body.remove(fixed_children[muc_luc_idx])
    # Delete TOC field paragraph right after it (if it's a paragraph)
    fixed_children = list(fixed_body)
    next_child = fixed_children[muc_luc_idx]  # now points to what was after MỤC LỤC
    next_texts = get_texts(next_child).strip()
    next_tag = next_child.tag.split('}')[-1]
    print(f'  Next after MỤC LỤC: {next_tag} [{next_texts[:60]}]')
    # Delete if it's the TOC field (contains fldChar) or empty placeholder
    if next_tag == 'p' and (
        next_child.find(f'.//{{{NS}}}fldChar') is not None or
        next_child.find(f'.//{{{NS}}}instrText') is not None or
        'TOC' in next_child.xml
    ):
        fixed_body.remove(next_child)
        print('  Deleted TOC field paragraph')

# ── Step 3: Delete PHỤ LỤC (from PHỤ LỤC A to end, keeping sectPr)
fixed_children = list(fixed_body)
phu_luc_idx = None
for i, child in enumerate(fixed_children):
    t = get_texts(child).strip()
    if t.startswith('PHỤ LỤC A'):
        phu_luc_idx = i
        break

print(f'PHỤ LỤC A found at body child {phu_luc_idx} (after step 2 deletion)')
if phu_luc_idx is not None:
    # Delete from phu_luc_idx to end, but keep sectPr (last child)
    last_child = fixed_children[-1]
    is_sect = last_child.tag.split('}')[-1] == 'sectPr'
    end_idx = len(fixed_children) - 1 if is_sect else len(fixed_children)
    for child in fixed_children[phu_luc_idx:end_idx]:
        fixed_body.remove(child)
    print(f'  Deleted {end_idx - phu_luc_idx} children (PHỤ LỤC + content)')

# ── Step 4: Insert source doc page 1 (children 0-N) at position 0
# Source page 1 = cover page only (up to but NOT including LỜI CẢM ƠN)
source_children = list(source_body)
# Find LỜI CẢM ƠN in source to know where cover page ends
source_page1_end = len(source_children)
for i, child in enumerate(source_children):
    t = get_texts(child).strip()
    if t == 'LỜI CẢM ƠN':
        source_page1_end = i  # Don't include LỜI CẢM ƠN or anything after
        break

print(f'Source page 1 (cover only): children 0 to {source_page1_end-1}')

# Insert in reverse order at position 0
for i in range(source_page1_end - 1, -1, -1):
    new_child = copy.deepcopy(source_children[i])
    fixed_body.insert(0, new_child)

print(f'Inserted {source_page1_end} children from source page 1')

# Save
fixed_doc.save('e:/test/DATN/YOLOv11_BaoCao_TiengViet_Result.docx')
print('Saved successfully to YOLOv11_BaoCao_TiengViet_Result.docx!')

# Verify
fixed_doc2 = Document('e:/test/DATN/YOLOv11_BaoCao_TiengViet_Result.docx')
body2 = fixed_doc2.element.body
children2 = list(body2)
print(f'Final body children count: {len(children2)}')
# Show first and last few
for i in range(min(5, len(children2))):
    tag = children2[i].tag.split('}')[-1]
    t = get_texts(children2[i]).strip()[:50]
    print(f'  child {i}: {tag} [{t}]')
print('  ...')
for i in range(max(0, len(children2)-5), len(children2)):
    tag = children2[i].tag.split('}')[-1]
    t = get_texts(children2[i]).strip()[:50]
    print(f'  child {i}: {tag} [{t}]')
