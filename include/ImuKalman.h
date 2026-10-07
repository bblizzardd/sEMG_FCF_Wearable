#pragma once

#include <math.h>
#include <stdint.h>

namespace ImuTuning {
// Process variance per second; measurement variance in g^2 or (deg/s)^2.
constexpr float ACCEL_Q = 0.02f;
constexpr float ACCEL_R = 0.0025f;
constexpr float GYRO_Q = 5.0f;
constexpr float GYRO_R = 0.25f;
// Angle/bias random walks and accelerometer angle measurement variance.
constexpr float ANGLE_Q = 0.05f;
constexpr float BIAS_Q = 0.003f;
constexpr float ANGLE_R = 4.0f;
constexpr float MAX_GAP_S = 0.25f;
constexpr float DEG = 57.2957795131f;
}

inline float wrapDegrees(float angle) {
  return angle - 360.0f * floorf((angle + 180.0f) / 360.0f);
}

class ScalarKalman {
 public:
  ScalarKalman(float q, float r) : q_(q), r_(r) {}
  void reset() { initialized_ = false; }
  float update(float measurement, float dt) {
    if (!initialized_) { x_ = measurement; p_ = r_; initialized_ = true; return x_; }
    p_ += q_ * dt;
    const float gain = p_ / (p_ + r_);
    x_ += gain * (measurement - x_);
    p_ *= 1.0f - gain;
    return x_;
  }
 private:
  float q_, r_, x_ = 0.0f, p_ = 0.0f;
  bool initialized_ = false;
};

// State [angle, gyro rate bias], measurement = accelerometer tilt.
class AngleKalman {
 public:
  void reset(float angle) { angle_ = angle; bias_ = 0; p00_ = 4; p01_ = p10_ = 0; p11_ = 1; }
  float angle() const { return angle_; }
  float update(float measurement, float rate, float dt, bool correct) {
    angle_ = wrapDegrees(angle_ + dt * (rate - bias_));
    p00_ += dt * (dt * p11_ - p01_ - p10_ + ImuTuning::ANGLE_Q);
    p01_ -= dt * p11_;
    p10_ -= dt * p11_;
    p11_ += ImuTuning::BIAS_Q * dt;
    if (correct) {
      const float innovation = wrapDegrees(measurement - angle_);
      const float variance = p00_ + ImuTuning::ANGLE_R;
      const float k0 = p00_ / variance, k1 = p10_ / variance;
      angle_ = wrapDegrees(angle_ + k0 * innovation);
      bias_ += k1 * innovation;
      const float old00 = p00_, old01 = p01_;
      p00_ -= k0 * old00; p01_ -= k0 * old01;
      p10_ -= k1 * old00; p11_ -= k1 * old01;
    }
    return angle_;
  }
 private:
  float angle_ = 0, bias_ = 0, p00_ = 4, p01_ = 0, p10_ = 0, p11_ = 1;
};

class ImuKalman {
 public:
  struct Output {
    float accel[3], gyro[3];
    float rollAccel = NAN, pitchAccel = NAN;
    float roll = NAN, pitch = NAN;
    bool accelTrusted = false;
  };
  void reset() {
    for (unsigned i = 0; i < 3; ++i) { accel_[i].reset(); gyro_[i].reset(); }
    previousUs_ = 0; initialized_ = false; attitudeReady_ = false;
  }
  Output update(const float *accel, const float *gyro, uint64_t hostUs) {
    float dt = initialized_ && hostUs > previousUs_ ? (hostUs - previousUs_) / 1000000.0f : 0.0f;
    if (dt <= 0.0f || dt > ImuTuning::MAX_GAP_S) { reset(); dt = 0.01f; }
    previousUs_ = hostUs; initialized_ = true;
    Output out;
    for (unsigned i = 0; i < 3; ++i) {
      out.accel[i] = accel_[i].update(accel[i], dt);
      out.gyro[i] = gyro_[i].update(gyro[i], dt);
    }
    const float norm = sqrtf(accel[0]*accel[0] + accel[1]*accel[1] + accel[2]*accel[2]);
    if (norm > 0.01f) {
      out.rollAccel = atan2f(accel[1], accel[2]) * ImuTuning::DEG;
      out.pitchAccel = atan2f(-accel[0], hypotf(accel[1], accel[2])) * ImuTuning::DEG;
    }
    // Reject strong linear acceleration and ill-conditioned tilt near +/-90 deg.
    out.accelTrusted = norm >= 0.85f && norm <= 1.15f && fabsf(out.pitchAccel) < 80.0f;
    if (!attitudeReady_) {
      if (!out.accelTrusted) return out;
      roll_.reset(out.rollAccel); pitch_.reset(out.pitchAccel); attitudeReady_ = true;
    } else {
      const float roll = roll_.angle() / ImuTuning::DEG;
      const float pitch = pitch_.angle() / ImuTuning::DEG;
      const float cp = cosf(pitch);
      if (fabsf(cp) < 0.17f) {
        attitudeReady_ = false;
        if (!out.accelTrusted) return out;
        roll_.reset(out.rollAccel); pitch_.reset(out.pitchAccel); attitudeReady_ = true;
      } else {
        // Body angular rates -> Euler roll/pitch rates. Use un-smoothed gyro to
        // avoid adding the scalar filter's delay to attitude prediction.
        const float rollRate = gyro[0] + tanf(pitch) * (sinf(roll)*gyro[1] + cosf(roll)*gyro[2]);
        const float pitchRate = cosf(roll)*gyro[1] - sinf(roll)*gyro[2];
        roll_.update(out.rollAccel, rollRate, dt, out.accelTrusted);
        pitch_.update(out.pitchAccel, pitchRate, dt, out.accelTrusted);
      }
    }
    out.roll = roll_.angle(); out.pitch = pitch_.angle();
    return out;
  }
 private:
  ScalarKalman accel_[3] = {{ImuTuning::ACCEL_Q, ImuTuning::ACCEL_R}, {ImuTuning::ACCEL_Q, ImuTuning::ACCEL_R}, {ImuTuning::ACCEL_Q, ImuTuning::ACCEL_R}};
  ScalarKalman gyro_[3] = {{ImuTuning::GYRO_Q, ImuTuning::GYRO_R}, {ImuTuning::GYRO_Q, ImuTuning::GYRO_R}, {ImuTuning::GYRO_Q, ImuTuning::GYRO_R}};
  AngleKalman roll_, pitch_;
  uint64_t previousUs_ = 0;
  bool initialized_ = false, attitudeReady_ = false;
};
