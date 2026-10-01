import contextlib
import csv
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import record_emg_csv


class FakeSerial:
    def __init__(self, payload):
        self.payload = payload
        self.closed = False

    @property
    def in_waiting(self):
        return len(self.payload)

    def read(self, size):
        if not self.payload:
            raise KeyboardInterrupt
        result, self.payload = self.payload[:size], self.payload[size:]
        return result

    def set_buffer_size(self, **kwargs):
        pass

    def close(self):
        self.closed = True


class RecorderTests(unittest.TestCase):
    def record(self, payload):
        device = FakeSerial(payload.encode())
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp) / 'capture.csv'
            with patch('sys.argv', ['record_emg_csv.py', 'COM_TEST', '-o', str(output)]), \
                 patch.object(record_emg_csv.serial, 'Serial', return_value=device) as open_port, \
                 patch.object(record_emg_csv.time, 'sleep'), \
                 contextlib.redirect_stdout(io.StringIO()) as log:
                record_emg_csv.main()
            open_port.assert_called_once_with('COM_TEST', 2000000, timeout=0.1)
            self.assertTrue(device.closed)
            with output.open(newline='') as stream:
                return list(csv.DictReader(stream)), log.getvalue()

    def test_batched_full_rate_stream_and_telemetry(self):
        payload = '[SPS] DRDY=2000.0 READ=2000.0 ADC_MISSED=0 QUEUE_DROP=0\n'
        payload += 'Raw: 12 | Env: 4\n'
        payload += ''.join(f'$D,{i+1},{100000+i*500},-100,200,0,0,0\n'
                           for i in range(2001))
        rows, log = self.record(payload)
        self.assertEqual(len(rows), 2001)
        self.assertEqual(rows[0]['time_s'], '0.000000')
        self.assertEqual(rows[-1]['time_s'], '1.000000')
        self.assertIn('2000.0 SPS', log)

    def test_reset_closes_recording_before_new_epoch(self):
        rows, log = self.record('$D,9000,10000000,0,0,0,0,0\n'
                                '$D,9001,10000500,0,0,0,0,0\n'
                                '$D,1,1700000,0,0,0,0,0\n')
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[-1]['time_s'], '0.000500')
        self.assertIn('2000.0 SPS', log)
        self.assertIn('khởi động lại', log)


if __name__ == '__main__':
    unittest.main()
