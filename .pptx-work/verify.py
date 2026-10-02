import json, hashlib, zipfile, xml.etree.ElementTree as ET
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8')
root = Path(__file__).resolve().parent
source = Path(r'C:\Users\Admin\Downloads\baocao_sEMG.pptx')
candidate = root / 'candidate.pptx'
ns = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def ordered_parts(z):
    rel = ET.fromstring(z.read('ppt/_rels/presentation.xml.rels'))
    ids = {x.get('Id'):x.get('Target') for x in rel}
    p = ET.fromstring(z.read('ppt/presentation.xml'))
    return ['ppt/'+ids[x.get('{'+ns['r']+'}id')] for x in p.find('p:sldIdLst',ns)]
def content(z, part):
    e = ET.fromstring(z.read(part))
    for shape in e.findall('.//p:sp',ns):
        name = shape.find('p:nvSpPr/p:cNvPr',ns)
        if name is not None and name.get('name','').startswith('Slide Number Placeholder'):
            for t in shape.findall('.//a:t',ns): t.text = ''
    return [t.text or '' for t in e.findall('.//a:t',ns) if t.text]
with zipfile.ZipFile(source) as a, zipfile.ZipFile(candidate) as b:
    sa,sb=ordered_parts(a),ordered_parts(b)
    assert len(sa)==56 and len(sb)==68
    original_matches=[]
    for i,p in enumerate(sa):
        j=i if i<51 else i+12
        assert content(a,p)==content(b,sb[j]), (i+1,j+1)
        original_matches.append([i+1,j+1])
    dims=ET.fromstring(b.read('ppt/presentation.xml')).find('p:sldSz',ns)
    assert (dims.get('cx'),dims.get('cy'))==('9144000','6858000')
    tables=sum(len(ET.fromstring(b.read(p)).findall('.//a:tbl',ns)) for p in sb[51:63])
    assert tables==9
    chartsA=[n for n in a.namelist() if n.startswith('ppt/charts/chart') and n.endswith('.xml')]
    chartsB=[n for n in b.namelist() if n.startswith('ppt/charts/chart') and n.endswith('.xml')]
    assert len(chartsA)==len(chartsB)==5
    chartvals=lambda z,n: [t.text for t in ET.fromstring(z.read(n)).findall('.//{http://schemas.openxmlformats.org/drawingml/2006/chart}v')]
    assert sorted([chartvals(a,n) for n in chartsA])==sorted([chartvals(b,n) for n in chartsB])
report={'status':'pass','slides':68,'added_slide_range':[52,63],
        'original_slide_content_matches':56,'original_charts_preserved':5,
        'new_native_tables':tables,'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
        'candidate_sha256':hashlib.sha256(candidate.read_bytes()).hexdigest(),
        'authoring_runtime':'Microsoft PowerPoint 16.0 COM',
        'artifact_tool_unavailable':True,
        'validation_limit':'PowerPoint render and native text bounds verified; artifact import unavailable.'}
(root/'content-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
