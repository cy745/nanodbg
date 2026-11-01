import ctypes
import unittest

from experiments.ble.windows_rfcomm_listener import _SockaddrBth


class SockaddrBthTests(unittest.TestCase):
    def test_windows_layout(self):
        self.assertEqual(ctypes.sizeof(_SockaddrBth), 30)
        self.assertEqual(_SockaddrBth.address.offset, 2)
        self.assertEqual(_SockaddrBth.service.offset, 10)
        self.assertEqual(_SockaddrBth.port.offset, 26)
