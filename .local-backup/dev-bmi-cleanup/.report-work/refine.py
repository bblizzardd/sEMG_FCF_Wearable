import json
from pathlib import Path

root = Path(__file__).resolve().parent
path = root / 'content.json'
spec = json.loads(path.read_text(encoding='utf-8'))
for page in spec['pages']:
    for block in page['blocks']:
        if block.get('type') == 'p':
            t = block['text']
            t = t.replace('mô hình FCF và RIR chạy trên ESP32', 'mô hình FCF (tỉ lệ số rep đã hoàn thành trong set đến failure) và RIR (số rep còn lại đến failure) chạy trên ESP32')
            t = t.replace('Velocity loss biểu diễn mức giảm vận tốc của một rep so với vận tốc tham chiếu trong set.', 'Velocity loss biểu diễn mức giảm vận tốc của một rep so với vận tốc tham chiếu trong set. Rep là một lần lặp động tác; set là một hiệp gồm nhiều rep.')
            t = t.replace('tốc độ ADC mục tiêu là 2000 SPS', 'tốc độ ADC mục tiêu là 2000 mẫu mỗi giây (SPS)')
            t = t.replace('Phần trăm kích hoạt dùng mức nền, gate, peak và độ nhạy thích nghi; chưa được hiệu chuẩn thành lực hoặc phần trăm MVC.', 'Phần trăm kích hoạt dùng mức nền, gate, peak và độ nhạy thích nghi; chưa được hiệu chuẩn thành lực hoặc phần trăm MVC (co cơ tối đa chủ động).')
            t = t.replace('Chuỗi xử lý đang dùng là high pass 20 Hz, notch 50 Hz, notch 100 Hz và low pass 450 Hz. Hai tầng Butterworth có bậc 2; mỗi notch là một biquad riêng. Đây là cấu hình dải mục tiêu cho sEMG trong project. Việc triển khai bộ lọc chưa xác nhận rằng nhiễu thực tế đã được loại hết.', 'Chuỗi xử lý đang dùng là high pass 20 Hz, notch 50 Hz, notch 100 Hz và low pass 450 Hz. High pass giảm DC và thành phần cử động chậm; notch giảm nhiễu điện lưới và hài; low pass giảm thành phần trên dải sEMG mục tiêu. Hai tầng Butterworth có bậc 2; mỗi notch là một biquad riêng. MPU giữ thông tin chuyển động ở tần số thấp, còn ADS giữ hoạt động điện cơ trong dải 20 đến 450 Hz. Các tần số cắt là vùng chuyển tiếp, nên bộ lọc không loại hết nhiễu ngoài dải.')
            t = t.replace('Các thuật toán velocity loss và thử nghiệm G3 trong báo cáo là công việc đề xuất, chưa được ghi nhận hoàn thành.', 'Thuật toán velocity loss và phép thử phát lại tín hiệu qua mạch trong báo cáo là công việc đề xuất, chưa được ghi nhận hoàn thành.')
            block['text'] = t
        if block.get('type') == 'list':
            block['items'] = [t.replace('Khóa định nghĩa vận tốc, tham chiếu VL và tiêu chí checkpoint G3 trước thử nghiệm đối chiếu.', 'Khóa định nghĩa vận tốc và tham chiếu VL. Với checkpoint G3, phát lại tín hiệu tham chiếu qua ADS và kiểm khả năng bảo toàn đặc trưng theo ngưỡng khai báo trước.') for t in block['items']]
        if block.get('type') == 'image':
            block['width'] = 5.55
            block['height'] = 4.94
path.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding='utf-8')
builder = root / 'build_docx.py'
s = builder.read_text(encoding='utf-8').replace('w:w="11906" w:h="16838"', 'w:w="12240" w:h="15840"')
builder.write_text(s, encoding='utf-8')
