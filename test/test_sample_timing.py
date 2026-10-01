import unittest

from sample_timing import SampleClock


class SampleClockTests(unittest.TestCase):
    def test_full_rate_independent_of_host_arrival_time(self):
        clock = SampleClock()
        for i in range(2001):
            self.assertFalse(clock.update(i + 1, 100000 + i * 500))
        self.assertEqual(clock.sps, 2000)
        self.assertEqual(clock.average_sps, 2000)
        self.assertEqual(clock.missing, 0)

    def test_adc_or_queue_loss_reduces_delivered_rate(self):
        clock = SampleClock()
        for i in range(1001):
            clock.update(i * 2 + 1, i * 1000)
        self.assertEqual(clock.sps, 1000)
        self.assertEqual(clock.missing, 1000)
        self.assertEqual(clock.last_gap_us, 1000)

    def test_uint32_wrap_does_not_reset(self):
        clock = SampleClock()
        clock.update(2**32 - 1, 2**32 - 250)
        self.assertFalse(clock.update(0, 250))
        self.assertEqual(clock.elapsed_us, 500)
        self.assertEqual(clock.missing, 0)
        self.assertEqual(clock.average_sps, 2000)

    def test_reboot_starts_new_segment(self):
        clock = SampleClock()
        clock.update(5000, 9000000)
        self.assertTrue(clock.update(1, 1700000))
        self.assertEqual(clock.samples, 1)
        self.assertEqual(clock.elapsed_us, 0)
        self.assertEqual(clock.sps, 0)

    def test_duplicate_rejected(self):
        clock = SampleClock()
        clock.update(1, 500)
        with self.assertRaises(ValueError):
            clock.update(1, 500)
        self.assertEqual(clock.samples, 1)


if __name__ == '__main__':
    unittest.main()
