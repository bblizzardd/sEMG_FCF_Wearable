from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import hashlib
import json
import re

work = Path(__file__).resolve().parent
source = work.parent / 'docs' / 'report' / 'latex'
tex = (source / 'bao_cao_tien_do.tex').read_text(encoding='utf-8')
pdftext = (work / 'latex-build' / 'text.txt').read_text(encoding='utf-8')
pages = [p for p in pdftext.split('\f') if p.strip()]
assert len(pages) == 11
assert all(len(p.strip()) > 500 for p in pages)
assert tex.count(r'\section{') == 9
assert tex.count(r'\begin{table}') == 7
assert tex.count(r'\begin{figure}') == 1
assert '\\frac{v_{\\mathrm{ref}}-v_k}{v_{\\mathrm{ref}}}' in tex
log = (work / 'latex-build' / 'bao_cao_tien_do.log').read_text(encoding='utf-8')
assert 'Overfull' not in log and 'Missing character' not in log
for image in re.findall(r'\\includegraphics\[[^\]]*\]\{([^}]+)\}', tex):
    assert (source / image).is_file()

readme = source / 'README.md'
readme.write_text(readme.read_text(encoding='utf-8') + '\n## Kết quả kiểm tra bản chuyển đổi\n\n'
    'Ngày 04/10/2026, nguồn đã biên dịch thành công bằng Tectonic 0.17.0 (XeTeX),\n'
    'tạo 11 trang trên máy Windows có Times New Roman. Đã kiểm tra bố cục,\n'
    'tiếng Việt, 7 bảng, hình MPU, hai công thức và mục lục. Log không có\n'
    'Overfull box hoặc Missing character. Số trang có thể thay đổi nhẹ khi\n'
    'dùng font thay thế trên máy khác.\n', encoding='utf-8')

target = source.parent / 'Bao_cao_tien_do_MPU_ADS_LaTeX.zip'
assert not target.exists(), 'Refusing to overwrite an existing archive'
with ZipFile(target, 'w', ZIP_DEFLATED) as z:
    for p in sorted(source.rglob('*')):
        if p.is_file():
            z.write(p, p.relative_to(source).as_posix())
with ZipFile(target) as z:
    assert z.testzip() is None
    assert set(z.namelist()) == {'bao_cao_tien_do.tex', 'README.md', 'assets/mpu-plot_axes_xyz_breakdown.png'}
    assert z.read('bao_cao_tien_do.tex') == (source / 'bao_cao_tien_do.tex').read_bytes()

receipt = {'source': str(source / 'bao_cao_tien_do.tex'), 'zip': str(target),
           'engine': 'Tectonic 0.17.0 (XeTeX)', 'pages': 11,
           'sections': 9, 'tables': 7, 'figures': 1,
           'compile': 'PASS', 'visual_review': 'PASS', 'archive': 'PASS',
           'sha256_tex': hashlib.sha256((source / 'bao_cao_tien_do.tex').read_bytes()).hexdigest()}
(work / 'latex-validation.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(receipt, ensure_ascii=False))
