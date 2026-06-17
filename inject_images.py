import re, os

SLIDES_DIR = r'C:\Using\DATN\pptx_unpacked\ppt\slides'
RELS_DIR   = r'C:\Using\DATN\pptx_unpacked\ppt\slides\_rels'
IMG_TYPE   = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image'
MEDIA_PRE  = '../media/'

# slide -> list of (rId, filename, x, y, cx, cy, pic_name)
# Coordinates in EMU. Slide = 12188952 x 6858000
ADDITIONS = {
    'slide3.xml': [
        ('rId10', 'fig_wf_muctieu.png', 400000, 4650000, 11400000, 1900000, 'Objective Workflow'),
    ],
    'slide5.xml': [
        ('rId10', 'fig_fisheye_camera.jpg', 6700000, 900000, 5100000, 4100000, 'Fisheye Camera'),
    ],
    'slide8.xml': [
        ('rId10', 'fig_wf_sahi.png', 400000, 4100000, 11400000, 2500000, 'SAHI Workflow'),
    ],
    'slide9.xml': [
        ('rId10', 'fig_fisheye8k.jpg', 6700000,  900000, 5100000, 3500000, 'FishEye8K Sample'),
        ('rId11', 'fig_pipeline.jpg',   400000, 5200000, 11400000, 1400000, 'Pipeline Diagram'),
    ],
    'slide12.xml': [
        ('rId10', 'fig_map_curves.jpg',    6400000,  850000, 5400000, 2800000, 'mAP Curves'),
        ('rId11', 'fig_wf_mapimprove.png', 400000,  4750000, 11400000, 1800000, 'Improvement Diagram'),
    ],
    'slide13.xml': [
        ('rId10', 'fig_system_arch.jpg', 400000, 4350000, 11400000, 2200000, 'System Architecture'),
    ],
    'slide14.xml': [
        ('rId10', 'fig_async_seq.jpg', 6300000, 850000, 5500000, 5600000, 'Async Sequence'),
    ],
    'slide15.xml': [
        ('rId10', 'fig_wf_its5module.png', 400000, 3850000, 11400000, 2750000, 'ITS Modules'),
    ],
    'slide19.xml': [
        ('rId10', 'fig_dashboard_ui.jpg', 6300000, 950000, 5500000, 3200000, 'Dashboard UI'),
    ],
    'slide23.xml': [
        ('rId10', 'fig_wf_roadmap.png', 400000, 4950000, 11400000, 1750000, 'Roadmap'),
    ],
}

PIC_TMPL = """      <p:pic>
        <p:nvPicPr>
          <p:cNvPr id="{pid}" name="{pname}" descr="{fname}"/>
          <p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>
          <p:nvPr/>
        </p:nvPicPr>
        <p:blipFill>
          <a:blip r:embed="{rid}"/>
          <a:stretch><a:fillRect/></a:stretch>
        </p:blipFill>
        <p:spPr>
          <a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>
          <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
        </p:spPr>
      </p:pic>"""

REL_TMPL = '  <Relationship Id="{rid}" Type="{rtype}" Target="{tgt}"/>'

for slide_name, additions in ADDITIONS.items():
    slide_path = os.path.join(SLIDES_DIR, slide_name)
    rels_path  = os.path.join(RELS_DIR, slide_name + '.rels')

    # Update .rels
    with open(rels_path, 'r', encoding='utf-8') as f:
        rels_xml = f.read()
    new_rels = ''
    for rid, fname, *_ in additions:
        if rid not in rels_xml:
            new_rels += '\n' + REL_TMPL.format(rid=rid, rtype=IMG_TYPE, tgt=MEDIA_PRE+fname)
    if new_rels:
        rels_xml = rels_xml.replace('</Relationships>', new_rels + '\n</Relationships>')
        with open(rels_path, 'w', encoding='utf-8') as f:
            f.write(rels_xml)
        print(f'rels updated: {slide_name}.rels')

    # Update slide XML
    with open(slide_path, 'r', encoding='utf-8') as f:
        slide_xml = f.read()
    ids = [int(m) for m in re.findall(r'cNvPr id="(\d+)"', slide_xml)]
    next_id = max(ids) + 1 if ids else 20
    pics_xml = ''
    for i, (rid, fname, x, y, cx, cy, pname) in enumerate(additions):
        if f'r:embed="{rid}"' not in slide_xml:
            pics_xml += '\n' + PIC_TMPL.format(
                pid=next_id+i, pname=pname, fname=fname,
                rid=rid, x=x, y=y, cx=cx, cy=cy)
    if pics_xml:
        slide_xml = slide_xml.replace('    </p:spTree>', pics_xml + '\n    </p:spTree>')
        with open(slide_path, 'w', encoding='utf-8') as f:
            f.write(slide_xml)
        print(f'slide  updated: {slide_name}  (+{len(additions)} image(s))')

print('All done.')
