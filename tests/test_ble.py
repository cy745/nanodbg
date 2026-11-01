import asyncio
import contextlib
import io
import sys
import types
import unittest
from unittest.mock import patch

from nanodbg.ble import parse_payload, scan, roundtrip, run_roundtrip

class BleTests(unittest.TestCase):
    def test_payload_validation(self):
        self.assertEqual(parse_payload('00ff80', 3), b'\x00\xff\x80')
        for value in ('', 'gg', '00112233'):
            with self.assertRaises(ValueError):
                parse_payload(value, 3)

    def test_roundtrip_preserves_order_and_rejects_duplicates(self):
        calls = []
        async def advertise(data, duration):
            calls.append(('send', data, duration))
        async def scan(data, duration):
            calls.append(('receive', data, duration))
        with patch('nanodbg.ble.advertise', advertise), patch('nanodbg.ble.scan', scan):
            with contextlib.redirect_stdout(io.StringIO()):
                asyncio.run(roundtrip([b'\x00', b'\xff']))
        self.assertEqual(calls, [('send', b'\x00', 8), ('receive', b'\x00', 18),
                                 ('send', b'\xff', 8), ('receive', b'\xff', 18)])
        with self.assertRaises(ValueError):
            run_roundtrip(['00', '00'])

    def test_scan_filters_and_counts_binary_payload(self):
        class Scanner:
            def __init__(self, detection_callback):
                self.callback = detection_callback
            async def __aenter__(self):
                self.callback(None, types.SimpleNamespace(manufacturer_data={0xffff: b'bad'}))
                self.callback(None, types.SimpleNamespace(manufacturer_data={0xffff: b'\x00\xff'}))
                self.callback(None, types.SimpleNamespace(manufacturer_data={0xffff: b'\x00\xff'}))
            async def __aexit__(self, *args):
                return False
        module = types.SimpleNamespace(BleakScanner=Scanner)
        output = io.StringIO()
        with patch.dict(sys.modules, {'bleak': module}), contextlib.redirect_stdout(output):
            asyncio.run(scan(b'\x00\xff', 0))
        self.assertIn('"payload_hex": "00ff"', output.getvalue())
        self.assertIn('"matches": 2', output.getvalue())
        self.assertNotIn('bad', output.getvalue())

if __name__ == '__main__':
    unittest.main()
