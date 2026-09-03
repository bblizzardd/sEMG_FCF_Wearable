#ifndef KALMAN_FILTER_H
#define KALMAN_FILTER_H

/**
 * @brief Bộ lọc Kalman 2-State cho MPU6050 (Attitude Estimation: Roll & Pitch)
 * Thuật toán chuẩn Kalman kết hợp Gia tốc kế (Góc tuyệt đối) và Con quay hồi
 * chuyển (Tốc độ góc) Khử trôi (drift) của Gyro và khử rung nhiễu (noise) của
 * Accel.
 */
class KalmanFilter {
private:
  /* Biến trạng thái */
  float angle; // Góc ước lượng hiện tại (độ)
  float bias;  // Độ lệch tĩnh (bias) của con quay hồi chuyển (độ/giây)
  float rate;  // Tốc độ góc không tải (unbiased rate)

  /* Ma trận hiệp phương sai sai số P */
  float P[2][2];

  /* Tham số nhiễu (Tuning parameters) */
  float Q_angle; // Phương sai nhiễu quá trình cho góc (mặc định: 0.001)
  float Q_bias;  // Phương sai nhiễu quá trình cho gyro bias (mặc định: 0.003)
  float
      R_measure; // Phương sai nhiễu đo lường từ accelerometer (mặc định: 0.03)

public:
  KalmanFilter() {
    Q_angle = 0.001f;
    Q_bias = 0.003f;
    R_measure = 0.03f;

    angle = 0.0f;
    bias = 0.0f;
    rate = 0.0f;

    P[0][0] = 0.0f;
    P[0][1] = 0.0f;
    P[1][0] = 0.0f;
    P[1][1] = 0.0f;
  }

  /**
   * @brief Cập nhật bộ lọc Kalman với giá trị đo mới
   * @param newAngle Góc đo được từ Accelerometer (độ)
   * @param newRate Tốc độ góc đo được từ Gyroscope (độ/giây)
   * @param dt Khoảng thời gian lấy mẫu (giây, ví dụ 0.01s cho 100Hz)
   * @return Góc ước lượng tối ưu sau khi lọc (độ)
   */
  float getAngle(float newAngle, float newRate, float dt) {
    // --- Bước 1: Tiên đoán trạng thái (Prediction Step) ---
    // \hat{x}_{k|k-1} = F * \hat{x}_{k-1|k-1} + B * u_k
    rate = newRate - bias;
    angle += dt * rate;

    // Cập nhật ma trận hiệp phương sai sai số: P_{k|k-1} = F * P_{k-1|k-1} *
    // F^T + Q
    P[0][0] += dt * (dt * P[1][1] - P[0][1] - P[1][0] + Q_angle);
    P[0][1] -= dt * P[1][1];
    P[1][0] -= dt * P[1][1];
    P[1][1] += Q_bias * dt;

    // --- Bước 2: Hiệu chỉnh đo lường (Measurement Update Step) ---
    // Đổi mới đo lường (Innovation / Measurement residual): y_k = z_k - H *
    // \hat{x}_{k|k-1}
    float y = newAngle - angle;

    // Hiệp phương sai đổi mới: S_k = H * P_{k|k-1} * H^T + R
    float S = P[0][0] + R_measure;

    // Hệ số Kalman Gain: K_k = P_{k|k-1} * H^T * S_k^{-1}
    float K[2];
    K[0] = P[0][0] / S;
    K[1] = P[1][0] / S;

    // Cập nhật trạng thái ước lượng: \hat{x}_{k|k} = \hat{x}_{k|k-1} + K_k *
    // y_k
    angle += K[0] * y;
    bias += K[1] * y;

    // Cập nhật ma trận hiệp phương sai: P_{k|k} = (I - K_k * H) * P_{k|k-1}
    float P00_temp = P[0][0];
    float P01_temp = P[0][1];

    P[0][0] -= K[0] * P00_temp;
    P[0][1] -= K[0] * P01_temp;
    P[1][0] -= K[1] * P00_temp;
    P[1][1] -= K[1] * P01_temp;

    return angle;
  }

  void setAngle(float newAngle) { angle = newAngle; }
  float getRate() const { return rate; }
  float getBias() const { return bias; }

  /* Cài đặt tham số nhiễu */
  void setQangle(float newQ_angle) { Q_angle = newQ_angle; }
  void setQbias(float newQ_bias) { Q_bias = newQ_bias; }
  void setRmeasure(float newR_measure) { R_measure = newR_measure; }

  float getQangle() const { return Q_angle; }
  float getQbias() const { return Q_bias; }
  float getRmeasure() const { return R_measure; }
};

/**
 * @brief Bộ lọc Kalman 1D (Scalar Kalman Filter) dùng để làm mượt tín hiệu trực
 * tiếp
 */
class Kalman1D {
private:
  float x; // Giá trị ước lượng
  float p; // Hiệp phương sai sai số
  float q; // Nhiễu quá trình (process noise)
  float r; // Nhiễu đo lường (measurement noise)
  float k; // Kalman gain

public:
  Kalman1D(float processNoise = 0.005f, float measurementNoise = 0.05f,
           float estimatedError = 1.0f, float initialValue = 0.0f) {
    q = processNoise;
    r = measurementNoise;
    p = estimatedError;
    x = initialValue;
  }

  float update(float measurement) {
    // Tiên đoán
    p = p + q;

    // Hiệu chỉnh
    k = p / (p + r);
    x = x + k * (measurement - x);
    p = (1.0f - k) * p;

    return x;
  }

  void setValue(float val) { x = val; }
  float getValue() const { return x; }
};

#endif // KALMAN_FILTER_H
