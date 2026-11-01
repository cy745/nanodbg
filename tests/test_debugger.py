import struct
import subprocess
import sys
import unittest

from nanodbg.__main__ import Debugger, REPORT, STUB
from nanodbg.transport import TransportError, nano7_usb_ids


class FakeTransport:
    def __init__(self, fingerprint=STUB):
        self.fingerprint = fingerprint
        self.calls = []
        self.magic = 0x32505452
        self.visible = 0
        self.report_ptr = 0x086d0000

    def command(self, cdb, data_in=0, allow_check=False):
        self.calls.append(cdb)
        if cdb[2] != 2:
            return b''
        address = int.from_bytes(cdb[3:7], 'big')
        result = bytearray(512)
        if address == 0x0819c400:
            result[88:176] = self.fingerprint
        elif address == REPORT:
            struct.pack_into('<I', result, 0x2c, self.magic)
            struct.pack_into('<3I', result, 0x50, 1, 1, 3)
            struct.pack_into('<I', result, 0x1d0, self.report_ptr)
        elif address == self.report_ptr:
            struct.pack_into('<10I', result, 0, 0x4742444e, 2, 0x086d0101,
                             1, 1, 0x086e0000, 240, 432, 12, self.visible)
        return bytes(result)


class DebuggerTests(unittest.TestCase):
    def test_handler_mismatch_refuses_commands(self):
        transport = FakeTransport(bytes(len(STUB)))
        with self.assertRaisesRegex(TransportError, 'handler mismatch'):
            Debugger(transport)
        self.assertEqual(len(transport.calls), 1)

    def test_report_validates_boot_magic_and_pointer(self):
        transport = FakeTransport()
        debugger = Debugger(transport)
        self.assertEqual(debugger.report()['app_id'], 12)
        transport.magic = 0
        with self.assertRaisesRegex(TransportError, 'magic mismatch'):
            debugger.report()
        transport.magic = 0x32505452
        transport.report_ptr = 0x10
        with self.assertRaisesRegex(TransportError, 'resident unavailable'):
            debugger.report()

    def test_tap_rejects_absent_surface_without_calling_device_code(self):
        transport = FakeTransport()
        debugger = Debugger(transport)
        with self.assertRaisesRegex(TransportError, 'active homebrew surface'):
            debugger.tap(10, 20)
        self.assertTrue(all(cdb[2] == 2 for cdb in transport.calls))

    def test_boot_status_reports_registration_and_checks_magic(self):
        transport = FakeTransport()
        debugger = Debugger(transport)
        report = debugger.boot_report()
        self.assertEqual((report['resident_started'], report['registration_completed'],
                          report['app_count']), (1, 1, 3))
        transport.magic = 0
        with self.assertRaisesRegex(TransportError, 'magic mismatch'):
            debugger.boot_report()

    def test_usb_parent_ids_exclude_interface_and_other_devices(self):
        ids = ('USB\\VID_05AC&PID_1267\\device-a\0'
               'USB\\VID_05AC&PID_1267&MI_00\\child\0'
               'USB\\VID_05AC&PID_1234\\other\0'
               'usb\\vid_05ac&pid_1267\\device-b\0\0')
        self.assertEqual(nano7_usb_ids(ids), [
            'USB\\VID_05AC&PID_1267\\device-a',
            'usb\\vid_05ac&pid_1267\\device-b'])
        self.assertEqual(nano7_usb_ids('\0'), [])

    def test_deploy_is_disabled_without_contacting_hardware(self):
        result = subprocess.run([sys.executable, '-m', 'nanodbg', 'deploy', '.'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Filesystem writes are disabled', result.stderr)


if __name__ == '__main__':
    unittest.main()
