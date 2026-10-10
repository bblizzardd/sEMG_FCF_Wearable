#include <assert.h>
#include <stdint.h>
#include "DebouncedButton.h"

int main() {
  DebouncedButton button;
  button.reset(false, 0);
  // Several contact bounces must produce one stable press.
  button.update(true, 10);
  button.update(false, 13);
  button.update(true, 16);
  button.update(true, 45);
  assert(!button.pressed());
  button.update(true, 46);
  assert(button.pressed());
  button.update(true, 1000);
  assert(button.pressed());
  // Release also needs a stable 30 ms, with no delay in the sampling loop.
  button.update(false, 1001);
  button.update(true, 1004);
  button.update(false, 1007);
  button.update(false, 1036);
  assert(button.pressed());
  button.update(false, 1037);
  assert(!button.pressed());
  // A short glitch cannot create a rep boundary.
  button.update(true, 1050);
  button.update(false, 1060);
  button.update(false, 1100);
  assert(!button.pressed());
  // Holding at boot is represented correctly; millis wrap is safe.
  button.reset(true, 0xFFFFFFF0u);
  assert(button.pressed());
  button.update(false, 0xFFFFFFF5u);
  button.update(false, 18);
  assert(button.pressed());
  button.update(false, 19);
  assert(!button.pressed());
}
