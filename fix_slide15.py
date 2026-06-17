import os

SLIDES_DIR = r'C:\Using\DATN\pptx_unpacked\ppt\slides'
RELS_DIR   = r'C:\Using\DATN\pptx_unpacked\ppt\slides\_rels'
IMG_TYPE   = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image'

slide_path = os.path.join(SLIDES_DIR, 'slide15.xml')
rels_path  = os.path.join(RELS_DIR,   'slide15.xml.rels')

# Add rId100 as image relationship
with open(rels_path, 'r', encoding='utf-8') as f:
    rels = f.read()
new_rel = f'  <Relationship Id="rId100" Type="{IMG_TYPE}" Target="../media/fig_wf_its5module.png"/>'
rels = rels.replace('</Relationships>', new_rel + '\n</Relationships>')
with open(rels_path, 'w', encoding='utf-8') as f:
    f.write(rels)
print('Fixed slide15.xml.rels')

# Fix the slide: only replace the first occurrence of rId10 inside a blipFill (the newly injected pic)
with open(slide_path, 'r', encoding='utf-8') as f:
    xml = f.read()
# Replace r:embed="rId10" -> rId100 (only one occurrence added by inject script)
xml = xml.replace('r:embed="rId10"', 'r:embed="rId100"', 1)
with open(slide_path, 'w', encoding='utf-8') as f:
    f.write(xml)
print('Fixed slide15.xml')
