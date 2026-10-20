from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
import json

ROOT=Path(__file__).resolve().parent
spec=json.loads((ROOT/'content.json').read_text(encoding='utf-8'))
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R='http://schemas.openxmlformats.org/officeDocument/2006/relationships'
M='http://schemas.openxmlformats.org/officeDocument/2006/math'
rels=[]
parts={}
def x(s): return escape(str(s))
def run(s,bold=False,size=None):
    pr='<w:rPr><w:color w:val="000000"/>'
    if bold: pr+='<w:b/>'
    if size: pr+=f'<w:sz w:val="{size}"/>'
    return f'<w:r>{pr}</w:rPr><w:t xml:space="preserve">{x(s)}</w:t></w:r>'
def para(s='',style='Normal',keep=False,align=None,page_before=False):
    pr=f'<w:pStyle w:val="{style}"/>'
    if page_before: pr+='<w:pageBreakBefore/>'
    if keep: pr+='<w:keepNext/>'
    if align: pr+=f'<w:jc w:val="{align}"/>'
    return f'<w:p><w:pPr>{pr}</w:pPr>{run(s)}</w:p>'
def table(block):
    widths=block['widths']; rows=block['rows']
    result=para(block.get('caption',''),'Caption',keep=True)
    borders=''.join(f'<w:{edge} w:val="single" w:sz="4" w:color="D9D9D9"/>' for edge in ['top','left','bottom','right','insideH','insideV'])
    result+=f'<w:tbl><w:tblPr><w:tblW w:w="9000" w:type="dxa"/><w:tblLayout w:type="fixed"/><w:tblBorders>{borders}</w:tblBorders><w:tblCellMar><w:top w:w="70" w:type="dxa"/><w:left w:w="105" w:type="dxa"/><w:bottom w:w="70" w:type="dxa"/><w:right w:w="105" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>'
    result+=''.join(f'<w:gridCol w:w="{n}"/>' for n in widths)+'</w:tblGrid>'
    for i,row in enumerate(rows):
        result+='<w:tr><w:trPr><w:cantSplit/>'+('<w:tblHeader/>' if i==0 else '')+'</w:trPr>'
        for j,val in enumerate(row):
            fill='333333' if i==0 else ('F4F4F4' if i%2==0 else 'FFFFFF')
            color='FFFFFF' if i==0 else '000000'
            align='center' if j==1 and len(val)<33 else 'left'
            result+=f'<w:tc><w:tcPr><w:tcW w:w="{widths[j]}" w:type="dxa"/><w:shd w:fill="{fill}"/><w:vAlign w:val="center"/></w:tcPr><w:p><w:pPr><w:spacing w:after="0" w:line="255" w:lineRule="auto"/><w:jc w:val="{align}"/></w:pPr><w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:sz w:val="22"/><w:color w:val="{color}"/>'+('<w:b/>' if i==0 else '')+f'</w:rPr><w:t>{x(val)}</w:t></w:r></w:p></w:tc>'
        result+='</w:tr>'
    return result+'</w:tbl>'+para('','Gap')
def mr(t): return f'<m:r><m:t>{x(t)}</m:t></m:r>'
def sub(base,index):
    return f'<m:sSub><m:e>{mr(base)}</m:e><m:sub>{mr(index)}</m:sub></m:sSub>'
def equation(kind):
    if kind=='vl':
        num=sub('v','ref')+mr('−')+sub('v','k')
        expr=sub('VL','k')+mr('=')+f'<m:f><m:num>{num}</m:num><m:den>{sub("v","ref")}</m:den></m:f>'+mr('×100%')
        return '<w:p><w:pPr><w:jc w:val="center"/><w:spacing w:before="70" w:after="120"/></w:pPr><m:oMathPara><m:oMath>'+expr+'</m:oMath></m:oMathPara></w:p>'
    return para('y[n] = b₀x[n] + b₁x[n−1] + b₂x[n−2] − a₁y[n−1] − a₂y[n−2]','Equation',align='center')
def image(block):
    rid='rId'+str(len(rels)+10)
    file=ROOT/block['file']; target='media/'+file.name
    rels.append((rid,'http://schemas.openxmlformats.org/officeDocument/2006/relationships/image',target,None))
    parts['word/'+target]=file.read_bytes()
    cx=round(block['width']*914400); cy=round(block['height']*914400)
    result=f'<w:p><w:pPr><w:jc w:val="center"/><w:keepNext/><w:spacing w:after="60"/></w:pPr><w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="1" name="MPU data plot" descr="Gia tốc và gyro theo ba trục cùng dấu nút bấm trong dữ liệu dev mpu"/><wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic><pic:nvPicPr><pic:cNvPr id="0" name="{x(file.name)}"/><pic:cNvPicPr/></pic:nvPicPr><pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill><pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>'
    return result+para(block['caption'],'Caption',keep=False)
def reference(block):
    rid='rId'+str(len(rels)+10)
    rels.append((rid,'http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink',block['url'],'External'))
    return para(block['text'],'Reference',keep=True)+f'<w:p><w:pPr><w:pStyle w:val="Reference"/><w:spacing w:after="130"/></w:pPr><w:hyperlink r:id="{rid}">{run(block["url"],size=21)}</w:hyperlink></w:p>'

styles=f'''<w:styles xmlns:w="{W}">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman" w:eastAsia="Times New Roman" w:cs="Times New Roman"/><w:sz w:val="24"/><w:color w:val="000000"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="110" w:line="276" w:lineRule="auto"/><w:widowControl/></w:pPr></w:pPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:pPr><w:jc w:val="both"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="350" w:after="220"/><w:jc w:val="center"/></w:pPr><w:rPr><w:b/><w:sz w:val="48"/><w:color w:val="000000"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="240"/><w:jc w:val="center"/></w:pPr><w:rPr><w:sz w:val="28"/><w:color w:val="000000"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:outlineLvl w:val="0"/><w:spacing w:before="0" w:after="160"/><w:jc w:val="left"/></w:pPr><w:rPr><w:b/><w:sz w:val="31"/><w:color w:val="000000"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="DocHeading"><w:name w:val="Doc Heading"/><w:basedOn w:val="Heading1"/><w:pPr><w:outlineLvl w:val="9"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:next w:val="Normal"/><w:pPr><w:keepNext/><w:outlineLvl w:val="1"/><w:spacing w:before="100" w:after="80"/><w:jc w:val="left"/></w:pPr><w:rPr><w:b/><w:sz w:val="26"/><w:color w:val="000000"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Caption"><w:name w:val="Caption"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="60" w:after="100"/><w:jc w:val="left"/></w:pPr><w:rPr><w:i/><w:sz w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Equation"><w:name w:val="Equation"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:before="80" w:after="110"/></w:pPr><w:rPr><w:rFonts w:ascii="Cambria Math" w:hAnsi="Cambria Math"/><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Reference"><w:name w:val="Reference"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="40" w:line="250" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="22"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="TOC1"><w:name w:val="toc 1"/><w:basedOn w:val="Normal"/><w:pPr><w:spacing w:after="70"/><w:jc w:val="left"/><w:tabs><w:tab w:val="right" w:leader="dot" w:pos="9000"/></w:tabs></w:pPr><w:rPr><w:sz w:val="23"/><w:color w:val="000000"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Gap"><w:name w:val="Gap"/><w:pPr><w:spacing w:after="40" w:line="40" w:lineRule="exact"/></w:pPr><w:rPr><w:sz w:val="4"/></w:rPr></w:style>
</w:styles>'''

body=para('TRƯỜNG ĐẠI HỌC BÁCH KHOA HÀ NỘI','Subtitle')
body+=para('THIẾT BỊ ĐEO THEO DÕI TIẾN TRÌNH MỎI CƠ','Subtitle')
body+=para(spec['title'],'Title')
body+=para(spec['subtitle'],'Subtitle')
body+=para('Báo cáo tiến độ kỹ thuật','Subtitle')
body+=para('Nhóm thực hiện','Normal',align='center')
for name in ['Trần Đức Trí','Trần Nguyễn Phúc Bình','Nguyễn Phú Minh']:
    body+=para(name,'Normal',align='center')
body+=para('','Normal')+para(spec['date'],'Normal',align='center')
body+=para('Hà Nội năm 2026','Normal',align='center')
for idx,page in enumerate(spec['pages']):
    body+=para(page['title'],'DocHeading' if idx==0 else 'Heading1',page_before=True)
    if page.get('toc'):
        body+='<w:p><w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> TOC \\o "1-1" \\h \\z </w:instrText></w:r><w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>Mục lục được cập nhật trong Word</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>'
    for b in page['blocks']:
        if b['type']=='p': body+=para(b['text'])
        elif b['type']=='h2': body+=para(b['text'],'Heading2')
        elif b['type']=='table': body+=table(b)
        elif b['type']=='image': body+=image(b)
        elif b['type']=='equation': body+=equation(b['kind'])
        elif b['type']=='reference': body+=reference(b)
        elif b['type']=='list':
            for i,s in enumerate(b['items'],1):
                body+=f'<w:p><w:pPr><w:ind w:left="300" w:hanging="300"/><w:spacing w:after="65"/></w:pPr>{run(str(i)+". "+s)}</w:p>'

body+='<w:sectPr><w:footerReference w:type="default" r:id="rIdFooter"/><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1701" w:header="567" w:footer="567"/><w:cols w:space="720"/></w:sectPr>'
document=f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W}" xmlns:r="{R}" xmlns:m="{M}" xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"><w:body>{body}</w:body></w:document>'
parts['word/document.xml']=document.encode()
parts['word/styles.xml']=styles.encode()
parts['word/settings.xml']=f'<w:settings xmlns:w="{W}"><w:updateFields w:val="false"/><w:zoom w:percent="100"/></w:settings>'.encode()
parts['word/footer1.xml']=f'<w:ftr xmlns:w="{W}"><w:p><w:pPr><w:jc w:val="center"/><w:spacing w:after="0"/></w:pPr><w:fldSimple w:instr=" PAGE "><w:r><w:rPr><w:sz w:val="20"/></w:rPr><w:t>1</w:t></w:r></w:fldSimple></w:p></w:ftr>'.encode()
relbase=[('rIdStyles','http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles','styles.xml',None),('rIdSettings','http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings','settings.xml',None),('rIdFooter','http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer','footer1.xml',None)]
relxml='<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
for rid,kind,target,mode in relbase+rels:
    relxml+=f'<Relationship Id="{rid}" Type="{kind}" Target="{x(target)}"'+(f' TargetMode="{mode}"' if mode else '')+'/>'
parts['word/_rels/document.xml.rels']=(relxml+'</Relationships>').encode()
parts['_rels/.rels']=b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'
parts['[Content_Types].xml']=b'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/><Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/></Types>'
out=ROOT/'candidate.docx'
with ZipFile(out,'w',ZIP_DEFLATED) as z:
    for name,data in parts.items(): z.writestr(name,data)
print(out)
