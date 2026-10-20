"""Convert the verified 03 October report into an editable LaTeX project."""
from pathlib import Path
import json
import re
import shutil

WORK = Path(__file__).resolve().parent
OUT = WORK.parent / 'docs' / 'report' / 'latex'
OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'assets').mkdir(exist_ok=True)
spec = json.loads((WORK / 'content.json').read_text(encoding='utf-8'))

ESC = {'\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$',
       '#': r'\#', '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}',
       '^': r'\textasciicircum{}', '²': r'\textsuperscript{2}',
       '±': r'\ensuremath{\pm}', '°': r'\ensuremath{^{\circ}}',
       'μ': r'\ensuremath{\mu}', 'π': r'\ensuremath{\pi}'}

def escape(s):
    return ''.join(ESC.get(c, c) for c in s)

def text(s):
    # Keep long identifiers and paths breakable without interpreting underscores.
    pieces = re.split(r'((?:[A-Za-z0-9]+[_.\/])+[A-Za-z0-9_.\/]+|\[[1-4]\]|v_ref|v_k)', s)
    out = []
    for p in pieces:
        if re.fullmatch(r'\[[1-4]\]', p):
            out.append(r'\hyperlink{ref' + p[1] + '}{' + p + '}')
        elif p == 'v_ref':
            out.append(r'\(v_{\mathrm{ref}}\)')
        elif p == 'v_k':
            out.append(r'\(v_k\)')
        elif re.fullmatch(r'(?:[A-Za-z0-9]+[_.\/])+[A-Za-z0-9_.\/]+', p):
            out.append(r'\path{' + p + '}')
        else:
            out.append(escape(p))
    return ''.join(out)

def caption(s):
    return text(re.sub(r'^(Bảng|Hình)\s+\d+\s+', '', s))

def table(b):
    fractions = [w / sum(b['widths']) for w in b['widths']]
    columns = '|'.join('>{\\raggedright\\arraybackslash}p{'+f'{f:.6f}'+r'\tablebodywidth}' for f in fractions)
    lines = [r'\begin{table}[H]', r'\centering', r'\caption{' + caption(b['caption']) + '}',
             r'\begingroup', r'\fontsize{10.5}{12.5}\selectfont', r'\setlength{\tabcolsep}{5pt}',
             r'\setlength{\tablebodywidth}{\dimexpr\linewidth-6\tabcolsep-4\arrayrulewidth\relax}',
             r'\renewcommand{\arraystretch}{1.2}', r'\arrayrulecolor{tableborder}',
             r'\begin{tabular}{|' + columns + '|}', r'\hline']
    for i, row in enumerate(b['rows']):
        if i == 0:
            lines += [r'\rowcolor{tablehead}', ' & '.join(r'{\color{white}\bfseries '+text(c)+'}' for c in row) + r' \\ \hline']
        else:
            if i % 2 == 0:
                lines.append(r'\rowcolor{tablerow}')
            lines.append(' & '.join(text(c) for c in row) + r' \\ \hline')
    lines += [r'\end{tabular}', r'\endgroup', r'\end{table}']
    return '\n'.join(lines)

preamble = r'''% !TeX program = xelatex
% Encoding: UTF-8. Compile twice with XeLaTeX or use latexmk -xelatex.
% Content snapshot: 03/10/2026; LaTeX conversion: 04/10/2026.
% Edit report metadata below. All figures use relative paths.
\documentclass[12pt,letterpaper]{article}
\usepackage{fontspec}
\IfFontExistsTF{Times New Roman}{\setmainfont{Times New Roman}}{\setmainfont{TeX Gyre Termes}}
\IfFontExistsTF{Arial}{\setsansfont{Arial}}{\setsansfont{TeX Gyre Heros}}
\IfFontExistsTF{Consolas}{\setmonofont{Consolas}[Scale=0.85]}{\setmonofont{Latin Modern Mono}[Scale=0.85]}
\usepackage[vietnamese]{babel}
\usepackage[left=3cm,right=2cm,top=2cm,bottom=2cm]{geometry}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage[table]{xcolor}
\usepackage{array,float}
\usepackage{caption}
\usepackage{enumitem}
\usepackage{setspace}
\usepackage{titlesec}
\usepackage{tocloft}
\usepackage{xurl}
\usepackage[unicode,hidelinks]{hyperref}

\definecolor{tablehead}{HTML}{333333}
\definecolor{tableborder}{HTML}{D9D9D9}
\definecolor{tablerow}{HTML}{F4F4F4}
\newlength{\tablebodywidth}
\setstretch{1.12}
\setlength{\parindent}{0pt}
\setlength{\parskip}{5pt}
\setlength{\intextsep}{8pt}
\setlength{\emergencystretch}{2em}
\setcounter{tocdepth}{1}
\setcounter{secnumdepth}{1}
\setlist[enumerate]{leftmargin=*,itemsep=3pt,topsep=4pt,parsep=0pt}
\titleformat{\section}{\color{black}\bfseries\fontsize{15.5}{18}\selectfont}{\thesection}{0.6em}{}
\titleformat{\subsection}{\color{black}\bfseries\fontsize{13}{15}\selectfont}{}{0pt}{}
\titlespacing*{\section}{0pt}{0pt}{8pt}
\titlespacing*{\subsection}{0pt}{7pt}{4pt}
\captionsetup{font=small,labelfont=bf,labelsep=space,justification=raggedright,singlelinecheck=false,skip=5pt}
\captionsetup[table]{position=top}
\renewcommand{\contentsname}{Mục lục}
\renewcommand{\tablename}{Bảng}
\renewcommand{\figurename}{Hình}
\renewcommand{\cftsecfont}{\normalfont}
\renewcommand{\cftsecpagefont}{\normalfont}
\renewcommand{\cftsecleader}{\cftdotfill{\cftdotsep}}
\setlength{\cftbeforesecskip}{4pt}
\setlength{\cftsecnumwidth}{1.5em}
\setlength{\cftbeforetoctitleskip}{0pt}
\setlength{\cftaftertoctitleskip}{8pt}
\hypersetup{pdftitle={Báo cáo tiến độ kỹ thuật hệ thống MPU6050 và ADS1292R},pdfauthor={Trần Đức Trí; Trần Nguyễn Phúc Bình; Nguyễn Phú Minh}}

\begin{document}
% ------------------------------------------------------------
% Cover page
% ------------------------------------------------------------
\begin{titlepage}
\centering
{\fontsize{14}{18}\selectfont TRƯỜNG ĐẠI HỌC BÁCH KHOA HÀ NỘI\par}
\vspace{0.6cm}
{\fontsize{14}{18}\selectfont THIẾT BỊ ĐEO THEO DÕI TIẾN TRÌNH MỎI CƠ\par}
\vspace{0.9cm}
{\fontsize{24}{29}\selectfont\bfseries Báo cáo tiến độ kỹ thuật hệ thống MPU6050 và ADS1292R\par}
\vspace{0.7cm}
{\fontsize{14}{18}\selectfont Thiết bị đeo theo dõi chuyển động và tín hiệu điện cơ trong bài tập kháng lực\par}
\vspace{0.5cm}
{\fontsize{14}{18}\selectfont Báo cáo tiến độ kỹ thuật\par}
\vspace{0.5cm}
Nhóm thực hiện\par
Trần Đức Trí\par
Trần Nguyễn Phúc Bình\par
Nguyễn Phú Minh\par
\vspace{0.6cm}
Ngày 03 tháng 10 năm 2026\par
Hà Nội năm 2026\par
\thispagestyle{plain}
\end{titlepage}
\setcounter{page}{2}
'''

chunks = [preamble]
for i, page in enumerate(spec['pages']):
    chunks += ['% ------------------------------------------------------------', '% ' + page['title'], '% ------------------------------------------------------------']
    if i == 0:
        chunks += [r'\tableofcontents', r'\vspace{5pt}']
    else:
        chunks += [r'\clearpage', r'\section{' + text(re.sub(r'^\d+\s+', '', page['title'])) + '}']
    if i == 8:
        # The dense verification section stays together without shrinking its text.
        chunks += [r'\begingroup', r'\setlength{\parskip}{3pt}']
    for b in page['blocks']:
        kind = b['type']
        if kind == 'p':
            chunks.append(text(b['text']) + '\n')
        elif kind == 'h2':
            chunks.append(r'\subsection*{' + text(b['text']) + '}')
        elif kind == 'table':
            chunks.append(table(b))
        elif kind == 'image':
            shutil.copy2(WORK / b['file'], OUT / 'assets' / b['file'])
            chunks.append(r'''\begin{figure}[H]
\centering
\includegraphics[width=0.86\linewidth]{assets/''' + b['file'] + r'''}
\caption{''' + caption(b['caption']) + r'''}
\label{fig:mpu-data}
\end{figure}''')
        elif kind == 'equation':
            if b['kind'] == 'vl':
                chunks.append(r'\[\mathrm{VL}_k=\frac{v_{\mathrm{ref}}-v_k}{v_{\mathrm{ref}}}\times100\%\]')
            else:
                chunks.append(r'\[y[n]=b_0x[n]+b_1x[n-1]+b_2x[n-2]-a_1y[n-1]-a_2y[n-2]\]')
        elif kind == 'list':
            chunks += [r'\begin{enumerate}'] + [r'\item '+text(t) for t in b['items']] + [r'\end{enumerate}']
        elif kind == 'reference':
            number = re.match(r'\[(\d)\]', b['text']).group(1)
            chunks.append(r'\hypertarget{ref'+number+'}{}'+escape(b['text']) + r'\par'+'\n'+r'\url{'+b['url']+r'}\par\medskip')
    if i == 8:
        chunks.append(r'\par\endgroup')
chunks.append(r'\end{document}')
tex = '\n\n'.join(chunks) + '\n'
(OUT / 'bao_cao_tien_do.tex').write_text(tex, encoding='utf-8')

readme = '''# Báo cáo tiến độ kỹ thuật MPU6050 và ADS1292R

Bản LaTeX chuyển từ báo cáo Word 11 trang đã lập ngày 03/10/2026.
Chuyển định dạng ngày 04/10/2026; giữ nguyên mốc nội dung, kết quả kiểm thử
và trạng thái hai nhánh trong bản Word. Các trao đổi mới về tụ và chuyển IMU
sang SPI chưa được bổ sung thành hạng mục đã triển khai.

## Các file

- `bao_cao_tien_do.tex`: toàn bộ nội dung, bảng, công thức và tài liệu tham khảo.
- `assets/mpu-plot_axes_xyz_breakdown.png`: hình dữ liệu MPU được trích từ nhánh dev-mpu.

Giữ nguyên cấu trúc thư mục để LaTeX tìm được hình. File mã nguồn là UTF-8.

## Biên dịch trên Overleaf

1. Tạo project từ file ZIP bằng Upload Project.
2. Chọn `bao_cao_tien_do.tex` làm Main document.
3. Trong Settings/Menu, chọn Compiler là **XeLaTeX**.
4. Recompile; nếu mục lục chưa cập nhật, biên dịch lại.

## Biên dịch trên máy

Chạy trong thư mục chứa file `.tex`, với TeX Live hoặc MiKTeX:

```powershell
xelatex -interaction=nonstopmode -halt-on-error bao_cao_tien_do.tex
xelatex -interaction=nonstopmode -halt-on-error bao_cao_tien_do.tex
```

Hoặc:

```powershell
latexmk -xelatex bao_cao_tien_do.tex
```

Không dùng pdfLaTeX vì nguồn sử dụng fontspec và tiếng Việt Unicode.
Nếu máy có Times New Roman thì báo cáo sử dụng font này; nếu không,
nguồn tự chọn TeX Gyre Termes. Font monospace cũng có phương án thay thế.
Chênh lệch font hoặc phiên bản gói có thể làm số trang thay đổi nhẹ.

## Chỉnh sửa

- Bìa và thông tin nhóm nằm sau `\\begin{document}`.
- Mỗi mục chính được đánh dấu bằng comment và `\\section{...}`.
- Đổi lề/khổ giấy trong `geometry` và tùy chọn `documentclass`.
- Chỉnh bảng ngay trong môi trường `tabular`; chỉnh công thức trong `\\[...\\]`.
- Nguồn không phụ thuộc file `.bib` ngoài; tài liệu tham khảo nằm ở mục cuối.
'''
(OUT / 'README.md').write_text(readme, encoding='utf-8')
print(OUT / 'bao_cao_tien_do.tex')
