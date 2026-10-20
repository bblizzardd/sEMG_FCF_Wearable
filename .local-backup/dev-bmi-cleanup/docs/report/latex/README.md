# Báo cáo tiến độ kỹ thuật MPU6050 và ADS1292R

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

- Bìa và thông tin nhóm nằm sau `\begin{document}`.
- Mỗi mục chính được đánh dấu bằng comment và `\section{...}`.
- Đổi lề/khổ giấy trong `geometry` và tùy chọn `documentclass`.
- Chỉnh bảng ngay trong môi trường `tabular`; chỉnh công thức trong `\[...\]`.
- Nguồn không phụ thuộc file `.bib` ngoài; tài liệu tham khảo nằm ở mục cuối.

## Kết quả kiểm tra bản chuyển đổi

Ngày 04/10/2026, nguồn đã biên dịch thành công bằng Tectonic 0.17.0 (XeTeX),
tạo 11 trang trên máy Windows có Times New Roman. Đã kiểm tra bố cục,
tiếng Việt, 7 bảng, hình MPU, hai công thức và mục lục. Log không có
Overfull box hoặc Missing character. Số trang có thể thay đổi nhẹ khi
dùng font thay thế trên máy khác.
