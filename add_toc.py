import sys, io, copy
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
from docx import Document
from docx.oxml.ns import qn
from lxml import etree

NS = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W = f'{{{NS}}}'

def get_texts(elem):
    return ''.join(r.text for r in elem.findall(f'.//{W}t') if r.text)

doc = Document('e:/test/DATN/YOLOv11_BaoCao_TiengViet_Result.docx')
body = doc.element.body
children = list(body)

# Find insertion point: before DANH MỤC TỪ VIẾT TẮT
insert_before_idx = None
for i, child in enumerate(children):
    if get_texts(child).strip() == 'DANH MỤC TỪ VIẾT TẮT':
        insert_before_idx = i
        break

print(f'Insert TOC before child {insert_before_idx} (DANH MỤC TỪ VIẾT TẮT)')

# Copy formatting from DANH MỤC TỪ VIẾT TẮT heading (same Heading1 + pageBreakBefore style)
danh_muc_elem = children[insert_before_idx]

# ── Build MỤC LỤC heading paragraph (clone from DANH MỤC and change text)
muc_luc_heading = copy.deepcopy(danh_muc_elem)
# Remove all text runs and replace with MỤC LỤC
for r in muc_luc_heading.findall(f'.//{W}r'):
    muc_luc_heading.remove(r)
# Find and remove existing runs properly
for r in list(muc_luc_heading):
    tag = r.tag.split('}')[-1]
    if tag == 'r':
        muc_luc_heading.remove(r)

# Create a new run with MỤC LỤC text
run_xml = f'''<w:r xmlns:w="{NS}">
  <w:rPr>
    <w:rFonts w:cs="Times New Roman" w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman"/>
    <w:b/>
    <w:sz w:val="28"/>
    <w:szCs w:val="28"/>
  </w:rPr>
  <w:t>MỤC LỤC</w:t>
</w:r>'''
run_elem = etree.fromstring(run_xml)
muc_luc_heading.append(run_elem)

# ── Build TOC field paragraph
# Standard Word TOC field: begin → instrText → separate → (entries) → end
# dirty="true" tells Word to auto-update when opened
toc_para_xml = f'''<w:p xmlns:w="{NS}">
  <w:pPr>
    <w:spacing w:line="400" w:lineRule="exact"/>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="Times New Roman"/>
      <w:sz w:val="26"/>
      <w:szCs w:val="26"/>
    </w:rPr>
  </w:pPr>
  <w:r>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="Times New Roman"/>
      <w:sz w:val="26"/>
      <w:szCs w:val="26"/>
    </w:rPr>
    <w:fldChar w:fldCharType="begin" w:dirty="true"/>
  </w:r>
  <w:r>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="Times New Roman"/>
      <w:sz w:val="26"/>
      <w:szCs w:val="26"/>
    </w:rPr>
    <w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText>
  </w:r>
  <w:r>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="Times New Roman"/>
      <w:sz w:val="26"/>
      <w:szCs w:val="26"/>
    </w:rPr>
    <w:fldChar w:fldCharType="separate"/>
  </w:r>
  <w:r>
    <w:rPr>
      <w:noProof/>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="Times New Roman"/>
      <w:sz w:val="26"/>
      <w:szCs w:val="26"/>
    </w:rPr>
    <w:t>Nhấn Ctrl+A rồi F9 để cập nhật mục lục tự động</w:t>
  </w:r>
  <w:r>
    <w:rPr>
      <w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:cs="Times New Roman" w:eastAsia="Times New Roman"/>
      <w:sz w:val="26"/>
      <w:szCs w:val="26"/>
    </w:rPr>
    <w:fldChar w:fldCharType="end"/>
  </w:r>
</w:p>'''
toc_para_elem = etree.fromstring(toc_para_xml)

# ── Insert both elements before DANH MỤC TỪ VIẾT TẮT
danh_muc_parent = danh_muc_elem.getparent()
danh_muc_pos = list(danh_muc_parent).index(danh_muc_elem)

danh_muc_parent.insert(danh_muc_pos, toc_para_elem)
danh_muc_parent.insert(danh_muc_pos, muc_luc_heading)

print(f'Inserted MỤC LỤC heading + TOC field before DANH MỤC TỪ VIẾT TẮT')

# Save
doc.save('e:/test/DATN/YOLOv11_BaoCao_TiengViet_Result.docx')
print('Saved successfully!')

# Verify structure
doc2 = Document('e:/test/DATN/YOLOv11_BaoCao_TiengViet_Result.docx')
body2 = doc2.element.body
children2 = list(body2)
print(f'Final body children: {len(children2)}')
print('Children 12-30:')
for i in range(12, min(32, len(children2))):
    tag = children2[i].tag.split('}')[-1]
    t = get_texts(children2[i]).strip()[:60]
    has_break = 'pageBreakBefore' in children2[i].xml
    toc = 'instrText' in children2[i].xml
    print(f'  child {i}: {tag} break={has_break} toc={toc} [{t}]')
