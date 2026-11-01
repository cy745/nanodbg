"""Native iPod nano debugger: python -m nanodbg --help."""
import argparse
import json
import os
import secrets
import struct
import sys
import time
import threading
from pathlib import Path

from .transport import discover, open_transport, TransportError

STUB = bytes.fromhex('feb5144605460026066010688168104688478678022e01d0a72e0bd1c278436812061bba1b0a1a43a72e06d11f20c0434008904770202870febd104601920121490202910722944646df02992068036901aa20469847febd')
REPORT = 0x086c9b84


class Debugger:
    def __init__(self, transport):
        self.transport = transport
        if self.read(0x0819c400)[88:176] != STUB:
            raise TransportError('Firmware handler mismatch; refusing commands')

    def read(self, address):
        return self.transport.command(bytes([0xc6, 0x96, 2]) + address.to_bytes(4, 'big') + bytes(3), 512)

    def boot_report(self):
        boot = self.read(REPORT)
        if struct.unpack_from('<I', boot, 0x2c)[0] != 0x32505452:
            raise TransportError('Boot report magic mismatch')
        offsets = {'resident_started': 0x50, 'registration_completed': 0x54,
                   'app_count': 0x58, 'preloaded_count': 0x5c,
                   'failure_mask': 0x60, 'launch_recorded': 0x64,
                   'launched_app_id': 0x68, 'launched_app_kind': 0x6c,
                   'launch_entry': 0x70, 'launch_count': 0xa8}
        return {name: struct.unpack_from('<I', boot, offset)[0]
                for name, offset in offsets.items()}

    def report(self):
        boot = self.read(REPORT)
        if struct.unpack_from('<I', boot, 0x2c)[0] != 0x32505452:
            raise TransportError('Boot report magic mismatch')
        ptr = struct.unpack_from('<I', boot, 0x1d0)[0]
        if not 0x08000000 <= ptr < 0x10000000:
            raise TransportError('Debugger resident unavailable')
        raw = self.read(ptr)
        fields = struct.unpack_from('<10I', raw)
        if fields[0] != 0x4742444e or fields[1] not in (1, 2):
            raise TransportError('Debugger report version mismatch')
        keys = ('magic', 'version', 'capture_fn', 'sequence', 'status',
                'pixels', 'width', 'height', 'app_id', 'app_visible')
        state = dict(zip(keys, fields))
        state['report_ptr'] = ptr
        if fields[1] == 2:
            ext = struct.unpack_from('<21I', raw, 40)
            state['touch_fn'] = ext[:19]
            state['touch_sequence'], state['touch_status'] = ext[19:]
        return state

    def call(self, address, state):
        if not address & 1 or abs((address & ~1) - state['report_ptr']) > 0x100000:
            raise TransportError('Entry outside resident image vicinity')
        self.transport.command(bytes([0xc6, 0x96, 0xa7]) + address.to_bytes(4, 'big') + bytes(3), allow_check=True)

    def wait_sequence(self, key, previous):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            time.sleep(.2)
            state = self.report()
            if state[key] != previous: return state
        raise TransportError(f'{key} did not advance')

    def screenshot(self, path):
        state = self.report()
        self.call(state['capture_fn'], state)
        result = self.wait_sequence('sequence', state['sequence'])
        w, h, addr = result['width'], result['height'], result['pixels']
        if result['status'] != 1 or not 0 < w <= 432 or not 0 < h <= 432 or w*h > 240*432 or not 0x08000000 <= addr < 0x10000000 or addr + w*h*4 > 0x10000000:
            raise TransportError(f'Invalid screenshot result: {result}')
        data = b''.join(self.read(addr + i) for i in range(0, w*h*4, 512))[:w*h*4]
        header = b'BM' + struct.pack('<IHHI', 54 + len(data), 0, 0, 54)
        header += struct.pack('<IiiHHIIiiII', 40, w, -h, 1, 32, 0, len(data), 2835, 2835, 0, 0)
        Path(path).write_bytes(header + data)
        return w, h

    def tap(self, x, y):
        state = self.report()
        if state['version'] < 2 or not (0 <= x < 240 and 0 <= y < 432 and state['app_visible']):
            raise TransportError('tap requires debugger v2, valid coordinates and an active homebrew surface')
        f = state['touch_fn']
        self.call(f[0], state)
        for bit in range(8):
            if x & (1 << bit): self.call(f[1 + bit], state)
        for bit in range(9):
            if y & (1 << bit): self.call(f[9 + bit], state)
        self.call(f[18], state)
        if self.wait_sequence('touch_sequence', state['touch_sequence'])['touch_status'] != 1:
            raise TransportError('Touch rejected by resident')


def windows_home(transport):
    if not transport.media_present():
        return False
    transport.lock_and_dismount()
    try:
        transport.command(bytes([0x1e, 0, 0, 0, 0, 0]))
        transport.command(bytes([0x1b, 1, 0, 0, 2, 0]))
    finally:
        transport.unlock()
    return True


def windows_disk(transport):
    changed = False
    if not transport.media_present():
        transport.command(bytes([0x1b, 1, 0, 0, 3, 0]))
        changed = True
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if transport.media_present():
            if changed:
                # Release the pre-mount volume handle so Windows can mount it.
                transport.close()
                while time.monotonic() < deadline:
                    try:
                        transport.reopen()
                        return
                    except OSError as exc:
                        if getattr(exc, 'winerror', None) != 21:
                            raise
                        time.sleep(.2)
                raise TransportError('iPod volume handle did not become available')
            return
        time.sleep(.2)
    raise TransportError('iPod media did not become available')


def windows_reboot(transport, path):
    # Establish a removal observation before triggering the panic reboot.
    from .transport import describe, usb_ipod_instances
    selected = discover()
    if (len(selected) != 1 or selected[0]['path'].lower() != path.lower()
            or not selected[0].get('serial')):
        raise TransportError('Cannot uniquely identify the iPod for reconnect monitoring')
    serial = selected[0]['serial']
    usb_devices = usb_ipod_instances()
    if len(usb_devices) != 1:
        raise TransportError('Expected exactly one nano 7 USB device for reconnect monitoring')
    usb_id = usb_devices[0].upper()
    windows_home(transport)
    gone = threading.Event()
    monitoring = threading.Event()
    stop = threading.Event()
    def monitor():
        while not stop.is_set():
            try:
                present = usb_id in (item.upper() for item in usb_ipod_instances())
                if present:
                    monitoring.set()
                elif monitoring.is_set():
                    gone.set()
            except (OSError, TransportError):
                pass
            stop.wait(.2)
    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    try:
        if not monitoring.wait(5):
            raise TransportError('Could not establish USB presence monitoring before reboot')
        # This intentionally triggers the existing experimental panic reboot.
        transport.command(bytes.fromhex('c696a70842d444000000'), allow_check=True)
        transport.close()
        deadline = time.monotonic() + 70
        while time.monotonic() < deadline:
            if gone.is_set() and usb_id in (item.upper() for item in usb_ipod_instances()):
                try:
                    info = describe(path)
                    matches = info and info.get('serial') == serial
                except OSError:
                    matches = False
                if matches:
                    try:
                        reconnected = open_transport(path)
                        try:
                            Debugger(reconnected)
                            windows_home(reconnected)
                            if reconnected.media_present():
                                raise TransportError('iPod returned but media is still present')
                            return
                        finally:
                            reconnected.close()
                    except OSError:
                        pass
            time.sleep(.3)
        raise TransportError('Could not confirm USB removal, return and Home mode')
    finally:
        stop.set()
        thread.join(timeout=2)


def windows_hci_request(transport, path, debugger, probe_file, opcode, params, timeout):
    """Run one request with the exact already-installed probe; leave evidence on failure."""
    from .hci import encode_request, parse_result
    if not (len(path)==6 and path.startswith('\\\\.\\') and path[4].isalpha() and path[5]==':'):
        raise TransportError('HCI probe requires a Windows drive-letter volume')
    if timeout <= 0:
        raise TransportError('timeout must be positive')
    request = encode_request(opcode, params, secrets.token_bytes(4))
    probe = Path(probe_file).read_bytes()
    root = Path(path[4:] + '\\') / 'Apps'
    request_path = root / 'Data' / 'hci-request.bin'
    result_path = root / 'Data' / 'hci-result.txt'

    def mounted(operation):
        windows_disk(transport)
        transport.close()
        try:
            deadline = time.monotonic() + 20
            while True:
                try:
                    # Media presence can precede filesystem readiness on Windows.
                    with (root / 'Executables' / 'BTRawProbe.hbapp').open('rb') as f:
                        f.read(1)
                    if (root / 'Data').is_dir():
                        break
                except OSError as exc:
                    if getattr(exc, 'winerror', None) not in (2, 3, 21):
                        raise
                if time.monotonic() >= deadline:
                    raise TransportError('Apps/Data did not become available')
                time.sleep(.25)
            return operation()
        finally:
            transport.reopen()
            windows_home(transport)

    def write_request():
        if ((root / 'Executables' / 'BTRawProbe.hbapp').read_bytes() != probe or
                (root / 'Startup' / 'autolaunch').read_bytes().strip() != b'BTRawProbe'):
            raise TransportError('Installed probe or autostart differs from supplied probe')
        if request_path.exists() or result_path.exists():
            raise TransportError('Existing HCI request/result preserved; inspect them before retrying')
        with request_path.open('xb') as f:
            f.write(request); f.flush(); os.fsync(f.fileno())
        if request_path.read_bytes() != request:
            raise TransportError('HCI request failed immediate verification')

    def verify_request():
        if request_path.read_bytes() != request:
            raise TransportError('HCI request failed fresh-mount verification')

    def read_and_cleanup():
        result = parse_result(result_path.read_bytes(), request)
        if request_path.read_bytes() != request:
            raise TransportError('HCI request changed; preserving device files')
        request_path.unlink()
        result_path.unlink()
        return result

    try:
        mounted(write_request)
        mounted(verify_request)
        print(f'HCI request {request[4:8].hex()} verified; rebooting', file=sys.stderr, flush=True)
        windows_reboot(transport, path)
        transport.reopen()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if debugger.report()['app_visible']:
                break
            time.sleep(.25)
        else:
            raise TransportError('HCI probe surface did not become visible')
        time.sleep(12)  # Includes the probe's startup and bounded Inquiry capture window.
        return mounted(read_and_cleanup)
    except (OSError, TransportError, ValueError) as exc:
        raise TransportError(f'{exc}; request/result may remain and replay on reboot; inspect before retrying') from exc


def main():
    parser = argparse.ArgumentParser(description='Native iPod nano 7 USB debugger (experimental firmware)')
    parser.add_argument('--device', help='explicit device path; default: detect a single Apple iPod')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('devices')
    sub.add_parser('status')
    sub.add_parser('boot-status', help='read resident boot and app registration report')
    wait_app = sub.add_parser('wait-app', help='wait for a visible homebrew surface')
    wait_app.add_argument('--timeout', type=float, default=45)
    sub.add_parser('home', help='flush/dismount the Windows volume and request the Home screen')
    sub.add_parser('reboot', help='experimental panic reboot and return to Home (Windows)')
    sub.add_parser('disk', help='make the Windows iPod volume available for development')
    deploy = sub.add_parser('deploy', help='experimental Windows deploy with backup and fresh-mount verification')
    deploy.add_argument('source', help='Apps directory containing AllApps.pack and app files')
    deploy.add_argument('--autostart', required=True, help='app executable name to autostart')
    deploy.add_argument('--backup-dir', default='nanodbg-backups')
    deploy.add_argument('--reboot', action='store_true')
    restore = sub.add_parser('restore', help='disabled: filesystem write path under investigation')
    restore.add_argument('backup')
    screen = sub.add_parser('screenshot')
    screen.add_argument('output', nargs='?', default='nano-screen.bmp')
    tap = sub.add_parser('tap')
    tap.add_argument('x', type=int)
    tap.add_argument('y', type=int)
    hci = sub.add_parser('hci-request', help='run one request using an already-installed experimental HCI probe (Windows)')
    hci.add_argument('opcode', help='hexadecimal HCI opcode')
    hci.add_argument('params', help='hexadecimal parameter bytes; use an empty string for none')
    hci.add_argument('--probe-file', required=True, help='exact installed BTRawProbe.hbapp to verify')
    hci.add_argument('--timeout', type=float, default=90, help='seconds to wait for probe surface after reboot')
    ble = sub.add_parser('ble', help='experimental short BLE advertisement tests')
    ble_sub = ble.add_subparsers(dest='ble_command', required=True)
    for action in ('scan', 'advertise'):
        command = ble_sub.add_parser(action)
        command.add_argument('payload_hex', help='expected or transmitted payload as hexadecimal bytes')
        command.add_argument('--duration', type=float, default=20)
    exchange = ble_sub.add_parser('roundtrip', help='run the two-window device echo experiment')
    exchange.add_argument('payload_hex', nargs='+', help='one or two distinct hex payloads')
    interactive = ble_sub.add_parser('interactive', help='exchange multiple messages with the runtime outbox probe')
    interactive.add_argument('--timeout', type=float, default=15, help='timeout per protocol step in seconds')
    interactive.add_argument('--probe', choices=('runtime', 'autonomous', 'queued'), default='runtime', help='deployed probe protocol')
    args = parser.parse_args()
    if args.command == 'ble' and args.ble_command == 'interactive':
        from .ble_duplex import run_interactive
        run_interactive(args.timeout, args.probe)
        return
    if args.command == 'ble':
        from .ble import run, run_roundtrip
        if args.ble_command == 'roundtrip':
            run_roundtrip(args.payload_hex)
        else:
            run(args.ble_command, args.payload_hex, args.duration)
        return
    if args.command == 'devices':
        print(json.dumps(discover(), indent=2))
        return
    if args.command == 'restore':
        raise TransportError('Automated restore remains disabled; use the saved backup manually.')
    if args.device:
        path = args.device
    else:
        devices = discover()
        if len(devices) != 1:
            raise TransportError(f'Expected one Apple iPod; found {len(devices)}. Use devices or --device.')
        path = devices[0]['path']
    transport = open_transport(path)
    try:
        debugger = Debugger(transport)
        if args.command == 'home':
            if sys.platform != 'win32':
                raise TransportError('home is currently implemented on Windows only')
            changed = windows_home(transport)
            print('Volume flushed and dismounted; Home requested' if changed else 'Media already ejected')
        elif args.command == 'reboot':
            if sys.platform != 'win32':
                raise TransportError('reboot is currently implemented on Windows only')
            windows_reboot(transport, path)
            print('Confirmed USB removal and return; media ejected')
        elif args.command == 'disk':
            if sys.platform != 'win32': raise TransportError('disk is currently implemented on Windows only')
            windows_disk(transport)
            print(f'iPod volume available at {path[4:]}')
        elif args.command == 'deploy':
            if sys.platform != 'win32':
                raise TransportError('deploy is currently implemented on Windows only')
            from .deploy import prepare, stage, verify
            entries = prepare(args.source, args.autostart)
            if not (len(path) == 6 and path.startswith('\\\\.\\') and path[4].isalpha() and path[5] == ':'):
                raise TransportError('deploy requires a Windows drive-letter volume')
            root = Path(path[4:] + '\\') / 'Apps'
            if Path(args.backup_dir).resolve().anchor.casefold() == root.anchor.casefold():
                raise TransportError('Backup directory must be on a different volume from the iPod')
            windows_disk(transport)
            transport.close()
            try:
                deadline = time.monotonic() + 20
                while not root.is_dir():
                    if time.monotonic() >= deadline:
                        raise TransportError('Apps directory did not become available')
                    time.sleep(.25)
                backup = stage(root, args.backup_dir, entries)
                print(f'Backed up original files to {backup}; ejecting for verification', flush=True)
            finally:
                transport.reopen()
                windows_home(transport)
            # Eject invalidates the old handle; close it before opening a new one.
            transport.close()
            transport.reopen()
            windows_disk(transport)
            transport.close()
            try:
                deadline = time.monotonic() + 20
                while not root.is_dir():
                    if time.monotonic() >= deadline:
                        raise TransportError('Apps directory did not become available for verification')
                    time.sleep(.25)
                verify(root, entries)
                print('All deployment files verified after eject and remount', flush=True)
            finally:
                transport.reopen()
                windows_home(transport)
            if args.reboot:
                windows_reboot(transport, path)
                print('Reboot confirmed; storage ejected. Use wait-app and boot-status to verify launch.')
        elif args.command == 'status':
            state = debugger.report()
            state.pop('touch_fn', None)
            print(json.dumps(state, indent=2))
        elif args.command == 'boot-status':
            print(json.dumps(debugger.boot_report(), indent=2))
        elif args.command == 'wait-app':
            if args.timeout <= 0: raise TransportError('timeout must be positive')
            deadline = time.monotonic() + args.timeout
            while time.monotonic() < deadline:
                state = debugger.report()
                if state['app_visible']:
                    print(f"Homebrew surface visible; app_id={state['app_id']}")
                    break
                time.sleep(.25)
            else:
                raise TransportError('No homebrew surface became visible before the timeout')
        elif args.command == 'screenshot':
            w, h = debugger.screenshot(args.output)
            print(f'{w}x{h} -> {args.output}')
        elif args.command == 'tap':
            debugger.tap(args.x, args.y)
            print(f'Homebrew touch injected at {args.x},{args.y}')
        elif args.command == 'hci-request':
            if sys.platform != 'win32':
                raise TransportError('hci-request is currently implemented on Windows only')
            result = windows_hci_request(transport, path, debugger, args.probe_file,
                                         int(args.opcode, 16), bytes.fromhex(args.params), args.timeout)
            print(json.dumps(result))
    finally:
        transport.close()


def cli():
    try:
        main()
    except (TransportError, OSError, ValueError) as exc:
        print(f'nanodbg: {exc}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    cli()
