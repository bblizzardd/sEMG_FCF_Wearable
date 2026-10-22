"""
combined_csv.py – File CSV gộp của một phiên ghi: sEMG (ADS1292R 2000 SPS) + IMU (BMI160 100 Hz)
+ trạng thái nút nhấn mốc Rep, cùng trục thời gian esp_timer của ESP32 (micro-giây).

Mỗi dòng là một mẫu sEMG. Các cột IMU giữ mẫu IMU gần nhất có imu_host_us <= timestamp_us
(IMU chậm hơn sEMG 20 lần nên một mẫu IMU lặp lại trên ~20 dòng; imu_seq đổi = mẫu IMU mới).
Cột IMU để trống khi IMU mất mẫu quá IMU_STALE_US. Mẫu IMU không dòng sEMG nào dùng tới
(lúc chưa có / mất sEMG) được ghi thành dòng riêng với cột sEMG để trống, nên không mất mẫu IMU nào.
"""

IMU_FIELDS = (
    "session,seq,host_us,sensor_ticks,ax_raw,ay_raw,az_raw,gx_raw,gy_raw,gz_raw,"
    "ax_g,ay_g,az_g,gx_dps,gy_dps,gz_dps,temp_c,ax_kal_g,ay_kal_g,az_kal_g,"
    "gx_kal_dps,gy_kal_dps,gz_kal_dps,roll_acc_deg,pitch_acc_deg,roll_kal_deg,pitch_kal_deg,"
    "accel_trusted,button_state"
).split(",")
IMU_LENGTHS = (17, 28, 29)  # firmware chưa có Kalman / chưa có nút / hiện tại

SEMG_COLUMNS = ["sample_idx", "ch2_raw24", "ch2_raw16", "ch2_filtered16", "lead_off"]
IMU_COLUMNS = [
    "ax_g", "ay_g", "az_g", "gx_dps", "gy_dps", "gz_dps",
    "ax_kal_g", "ay_kal_g", "az_kal_g", "gx_kal_dps", "gy_kal_dps", "gz_kal_dps",
    "roll_acc_deg", "pitch_acc_deg", "roll_kal_deg", "pitch_kal_deg", "accel_trusted",
]
COLUMNS = ["time_s", "timestamp_us", *SEMG_COLUMNS, "imu_seq", "imu_host_us", *IMU_COLUMNS, "button_state"]

IMU_STALE_US = 50_000  # 5 chu kỳ 100 Hz không có mẫu mới: coi như IMU đã mất
FLUSH_ROWS = 2000      # ~1 giây dữ liệu

_IMU_INDEX = [IMU_FIELDS.index(name) for name in IMU_COLUMNS]
_BUTTON_INDEX = IMU_FIELDS.index("button_state")
_NO_SEMG = "," * (len(SEMG_COLUMNS) - 1)
_NO_IMU = "," * (len(IMU_COLUMNS) + 1)  # imu_seq + imu_host_us + IMU_COLUMNS


class _ImuSample:
    __slots__ = ("host_us", "text", "button", "used")

    def __init__(self, host_us, text, button):
        self.host_us = host_us
        self.text = text
        self.button = button
        self.used = False


class CombinedWriter:
    """Ghi file gộp theo thứ tự dòng Serial; chịu được sEMG/IMU lệch nhau 1-2 mẫu ở ranh giới."""

    def __init__(self, file):
        self.file = file
        self.rows = 0
        self._t0 = None
        self._prev = None
        self._cur = None
        file.write(",".join(COLUMNS) + "\n")

    def add_imu(self, fields):
        """fields: các trường (chuỗi) của một dòng IMU firmware. Trả về False nếu dòng hỏng."""
        if len(fields) not in IMU_LENGTHS:
            return False
        try:
            seq = int(fields[1])
            host_us = int(fields[2])
        except ValueError:
            return False
        values = [fields[i] if i < len(fields) else "" for i in _IMU_INDEX]
        button = fields[_BUTTON_INDEX] if len(fields) > _BUTTON_INDEX else ""
        if self._cur is not None and not self._cur.used:
            self._write(self._cur.host_us, _NO_SEMG, self._cur.text, self._cur.button)
        self._prev, self._cur = self._cur, _ImuSample(host_us, ",".join([str(seq), str(host_us), *values]), button)
        return True

    def add_semg(self, sample_idx, timestamp_us, ch2_raw24, ch2_raw16, ch2_filtered16, lead_off, button=""):
        """button: cột button_state của dòng $D ("" với firmware cũ: lấy theo mẫu IMU)."""
        imu = self._imu_at(timestamp_us)
        if imu is not None:
            imu.used = True
            if button == "":
                button = imu.button
        self._write(timestamp_us, f"{sample_idx},{ch2_raw24},{ch2_raw16},{ch2_filtered16},{lead_off}",
                    imu.text if imu is not None else _NO_IMU, button)

    def close(self):
        """Ghi nốt mẫu IMU cuối nếu chưa dòng nào dùng tới. Không đóng file."""
        if self._cur is not None and not self._cur.used:
            self._cur.used = True
            self._write(self._cur.host_us, _NO_SEMG, self._cur.text, self._cur.button)
        self.file.flush()

    def _imu_at(self, timestamp_us):
        # Dòng sEMG có thể tới sau dòng IMU dù lấy mẫu trước đó một chút: khi đó dùng mẫu IMU trước
        for imu in (self._cur, self._prev):
            if imu is not None and imu.host_us <= timestamp_us:
                return imu if timestamp_us - imu.host_us <= IMU_STALE_US else None
        return None

    def _write(self, timestamp_us, semg_text, imu_text, button):
        if self._t0 is None:
            self._t0 = timestamp_us
        self.file.write(f"{(timestamp_us - self._t0) / 1e6:.6f},{timestamp_us},{semg_text},{imu_text},{button}\n")
        self.rows += 1
        if self.rows % FLUSH_ROWS == 0:
            self.file.flush()
