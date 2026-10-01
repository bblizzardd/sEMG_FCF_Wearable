"""Measure delivered sample rate from ESP32 timestamps, not USB arrival bursts."""


class SampleClock:
    def __init__(self):
        self.last_seq = None
        self.last_us = None
        self.samples = 0
        self.elapsed_us = 0
        self.missing = 0
        self.last_gap_us = 0
        self.last_missing = 0
        self.sps = 0.0
        self._window_us = 0
        self._window_intervals = 0

    @property
    def average_sps(self):
        return ((self.samples - 1) * 1_000_000 / self.elapsed_us
                if self.elapsed_us else 0.0)

    def update(self, sequence, timestamp_us):
        """Return True on restart; uint32 counter wrap is not a restart.

        A backward sequence or timestamp jump larger than half its range
        starts a new segment. Callers must not join recordings across a reset.
        """
        if not (0 <= sequence < 2**32 and 0 <= timestamp_us < 2**32):
            raise ValueError("Sample counters must be uint32")
        restarted = False
        self.last_gap_us = self.last_missing = 0
        if self.last_seq is not None:
            step = (sequence - self.last_seq) % 2**32
            gap = (timestamp_us - self.last_us) % 2**32
            if step >= 2**31 or gap >= 2**31:
                self.__init__()
                restarted = True
            elif step == 0 or gap == 0:
                raise ValueError("Duplicate sequence or timestamp")
            else:
                self.last_gap_us = gap
                self.last_missing = step - 1
                self.missing += self.last_missing
                self.elapsed_us += gap
                self._window_us += gap
                self._window_intervals += 1
                if self._window_us >= 1_000_000:
                    self.sps = self._window_intervals * 1_000_000 / self._window_us
                    self._window_us = self._window_intervals = 0
        self.last_seq = sequence
        self.last_us = timestamp_us
        self.samples += 1
        return restarted
