#include "ImuKalman.h"
#include <cassert>
#include <cmath>
#include <iostream>

int main() {
  // Stationary noise: lower variance after filtering, no artificial zero startup.
  ScalarKalman scalar(ImuTuning::ACCEL_Q, ImuTuning::ACCEL_R);
  assert(scalar.update(1.0f, 0.01f) == 1.0f);
  double inputPower = 0, outputPower = 0;
  for (int i=0; i<1000; ++i) {
    const float measured = 1.0f + (i%2 ? 0.05f : -0.05f);
    const float filtered = scalar.update(measured, 0.01f);
    if (i>100) { inputPower += (measured-1)*(measured-1); outputPower += (filtered-1)*(filtered-1); }
  }
  assert(outputPower < inputPower * 0.2);
  float step=0;
  for(int i=0;i<30;++i) step=scalar.update(2.0f,0.01f);
  assert(std::fabs(step-2.0f)<0.01f);

  ImuKalman filter;
  float accel[]={0,0,1}, gyro[]={0,0,0};
  auto output=filter.update(accel,gyro,10000);
  assert(output.accelTrusted && std::fabs(output.roll)<0.001 && std::fabs(output.pitch)<0.001);
  // Seed the actual orientation instead of slowly drifting up from zero.
  filter.reset();
  accel[1]=0.5f; accel[2]=std::sqrt(0.75f);
  output=filter.update(accel,gyro,20000);
  assert(std::fabs(output.roll-30)<0.01);
  // When acceleration isn't gravity-like, predict from gyro without bad correction.
  accel[0]=0; accel[1]=0; accel[2]=2;
  output=filter.update(accel,gyro,30000);
  assert(!output.accelTrusted && std::fabs(output.roll-30)<0.01);
  // Missing data must reseed covariance and attitude on the next valid frame.
  accel[0]=0; accel[1]=0; accel[2]=1;
  output=filter.update(accel,gyro,1000000);
  assert(std::fabs(output.roll)<0.001 && std::fabs(output.accel[2]-1)<0.001);
  filter.reset();
  accel[2]=0;
  output=filter.update(accel,gyro,1010000);
  assert(!output.accelTrusted && std::isnan(output.roll));
  accel[2]=1;
  output=filter.update(accel,gyro,1020000);
  assert(output.accelTrusted && std::isfinite(output.roll));
  // Angle innovations take the short route across +/-180 degrees.
  AngleKalman angle;
  angle.reset(179);
  const float crossed=angle.update(-179,0,0.01f,true);
  assert(std::fabs(wrapDegrees(crossed-179))<3);
  // Bias estimation prevents constant stationary gyro bias from accumulating.
  angle.reset(0);
  for(int i=0;i<4000;++i) angle.update(0,2,0.01f,true);
  assert(std::fabs(angle.angle())<0.5);
  std::cout << "Kalman behavior tests passed\n";
}
