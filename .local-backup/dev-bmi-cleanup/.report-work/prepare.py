from pathlib import Path
import subprocess, csv, io, json, zipfile, xml.etree.ElementTree as ET
root=Path(__file__).resolve().parent
root.mkdir(exist_ok=True)
for name in ['src/main.cpp','platformio.ini','data/data.csv','data/plot_axes_xyz_breakdown.png']:
    data=subprocess.check_output(['git','show','dev-mpu:'+name])
    (root / ('mpu-'+Path(name).name)).write_bytes(data)
rows=list(csv.DictReader(io.StringIO((root/'mpu-data.csv').read_text(encoding='utf-8'))))
deltas=[int(rows[i]['timestamp_ms'])-int(rows[i-1]['timestamp_ms']) for i in range(1,len(rows))]
summary={'branch':'dev-mpu','commit':'d2aaa81','rows':len(rows),'duration_s':(int(rows[-1]['timestamp_ms'])-int(rows[0]['timestamp_ms']))/1000,'delta_ms':sorted(set(deltas)),'pressed_rows':sum(r['button']=='1' for r in rows)}
(root/'mpu-evidence.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
print(json.dumps(summary))
deck=root.parent/'docs/presentation/baocao_sEMG_MPU_ADS_cap_nhat.pptx'
with zipfile.ZipFile(deck) as z:
    ns={'a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
    texts=[t.text for t in ET.fromstring(z.read('ppt/slides/slide1.xml')).findall('.//a:t',ns)]
    print('Cover text:', json.dumps(texts,ensure_ascii=False))
