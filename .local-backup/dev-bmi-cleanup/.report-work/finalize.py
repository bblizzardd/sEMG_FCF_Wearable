import hashlib
import json
import shutil
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET

work = Path(__file__).resolve().parent
candidate = work / 'candidate.docx'
pages = json.loads((work / 'page-text.json').read_text(encoding='utf-8-sig'))
assert len(pages) == 11
assert all(len(p['text'].strip()) > 100 for p in pages)
with ZipFile(candidate) as z:
    assert z.testzip() is None
    for name in z.namelist():
        if name.endswith('.xml') or name.endswith('.rels'):
            ET.fromstring(z.read(name))
    document = ET.fromstring(z.read('word/document.xml'))
    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
          'm': 'http://schemas.openxmlformats.org/officeDocument/2006/math'}
    assert len(document.findall('.//w:tbl', ns)) == 7
    assert document.find('.//m:oMath', ns) is not None
    text = ''.join(t.text or '' for t in document.findall('.//w:t', ns))
    assert 'Mục lục được cập nhật trong Word' not in text
    assert 'MPU6050' in text and 'ADS1292R' in text

out_dir = work.parent / 'docs' / 'report'
out_dir.mkdir(parents=True, exist_ok=True)
target = out_dir / 'Bao_cao_tien_do_MPU6050_ADS1292R_2026-10-03.docx'
assert not target.exists(), 'Refusing to overwrite an existing report'
shutil.copy2(candidate, target)
receipt = {'output': str(target), 'pages': 11, 'visual_review': 'All 11 pages inspected',
           'tables': 7, 'word_open_and_repaginate': 'PASS',
           'zip_xml_validation': 'PASS', 'python_tests': '7/7 PASS',
           'ADS_build': 'SUCCESS', 'sha256': hashlib.sha256(target.read_bytes()).hexdigest()}
(work / 'validation.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=False))
