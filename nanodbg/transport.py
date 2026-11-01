"""Native SCSI transports. No shell utilities or third-party packages."""
import ctypes as C
import os
import sys


class TransportError(RuntimeError):
    pass


def nano7_usb_ids(multisz):
    """Select nano 7 parent IDs, excluding USB interface children."""
    return [s for s in multisz.split('\0')
            if s.upper().startswith('USB\\VID_05AC&PID_1267\\')]


if sys.platform == 'win32':
    from ctypes import wintypes as W

    class Spt(C.Structure):
        _fields_ = [('Length', W.WORD), ('ScsiStatus', W.BYTE), ('PathId', W.BYTE),
                    ('TargetId', W.BYTE), ('Lun', W.BYTE), ('CdbLength', W.BYTE),
                    ('SenseInfoLength', W.BYTE), ('DataIn', W.BYTE),
                    ('DataTransferLength', W.DWORD), ('TimeOutValue', W.DWORD),
                    ('DataBuffer', C.c_void_p), ('SenseInfoOffset', W.DWORD),
                    ('Cdb', W.BYTE * 16)]

    class SptBuffer(C.Structure):
        _fields_ = [('spt', Spt), ('filler', W.ULONG), ('sense', W.BYTE * 32)]

    k = C.WinDLL('kernel32', use_last_error=True)
    k.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
    k.CreateFileW.restype = W.HANDLE
    k.DeviceIoControl.argtypes = [W.HANDLE, W.DWORD, C.c_void_p, W.DWORD,
                                  C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p]
    k.DeviceIoControl.restype = W.BOOL
    k.CloseHandle.argtypes = [W.HANDLE]
    k.GetLogicalDrives.restype = W.DWORD
    cfg = C.WinDLL('cfgmgr32')
    cfg.CM_Get_Device_ID_List_SizeW.argtypes = [C.POINTER(W.ULONG), W.LPCWSTR, W.ULONG]
    cfg.CM_Get_Device_ID_List_SizeW.restype = W.ULONG
    cfg.CM_Get_Device_ID_ListW.argtypes = [W.LPCWSTR, C.POINTER(C.c_wchar), W.ULONG, W.ULONG]
    cfg.CM_Get_Device_ID_ListW.restype = W.ULONG

    def usb_ipod_instances():
        """Read present USB PnP IDs without enumerating or opening volumes."""
        # Filter by the USB enumerator, and exclude not-present devices.
        flags = 0x001 | 0x100  # CM_GETIDLIST_FILTER_ENUMERATOR | FILTER_PRESENT
        for _ in range(4):
            size = W.ULONG()
            rc = cfg.CM_Get_Device_ID_List_SizeW(C.byref(size), 'USB', flags)
            if rc:
                raise TransportError(f'USB PnP enumeration failed: CONFIGRET 0x{rc:x}')
            buf = C.create_unicode_buffer(size.value)
            rc = cfg.CM_Get_Device_ID_ListW('USB', buf, size.value, flags)
            if rc == 0x1a:  # CR_BUFFER_SMALL if devices changed between calls
                continue
            if rc:
                raise TransportError(f'USB PnP enumeration failed: CONFIGRET 0x{rc:x}')
            return nano7_usb_ids(''.join(buf[:]))
        raise TransportError('USB PnP enumeration repeatedly changed')

    def ioctl(handle, code, inp=None, out=None):
        done = W.DWORD()
        ok = k.DeviceIoControl(handle, code, C.byref(inp) if inp is not None else None,
             C.sizeof(inp) if inp is not None else 0, C.byref(out) if out is not None else None,
             C.sizeof(out) if out is not None else 0, C.byref(done), None)
        if not ok:
            raise C.WinError(C.get_last_error())
        return done.value

    def open_handle(path, access):
        handle = k.CreateFileW(path, access, 3, None, 3, 0, None)
        if handle == W.HANDLE(-1).value:
            raise C.WinError(C.get_last_error())
        return handle

    def describe(path):
        handle = open_handle(path, 0)
        try:
            query = (C.c_ubyte * 12)()  # StorageDeviceProperty, PropertyStandardQuery
            buf = (C.c_ubyte * 1024)()
            n = ioctl(handle, 0x2d1400, query, buf)
            raw = bytes(buf[:n])
            if len(raw) < 36:
                return None
            import struct
            vendor, product, revision, serial, bus = struct.unpack_from('<IIIII', raw, 12)
            def string(offset):
                return raw[offset:].split(b'\0', 1)[0].decode('ascii', 'replace').strip() if 0 < offset < len(raw) else ''
            return {'path': path, 'vendor': string(vendor), 'product': string(product),
                    'serial': string(serial), 'bus': bus}
        finally:
            k.CloseHandle(handle)

    def discover():
        result = []
        mask = k.GetLogicalDrives()
        for i in range(26):
            if not mask & (1 << i):
                continue
            path = '\\\\.\\' + chr(65 + i) + ':'
            try:
                info = describe(path)
                if info and info['bus'] == 7 and info['vendor'].lower() == 'apple' and info['product'].lower().startswith('ipod'):
                    result.append(info)
            except OSError:
                continue
        return result

    class WindowsTransport:
        def __init__(self, path):
            self.path = path
            self.handle = open_handle(path, 0xc0000000)

        def close(self):
            if self.handle:
                k.CloseHandle(self.handle)
                self.handle = None

        def reopen(self):
            new = open_handle(self.path, 0xc0000000)
            self.close()
            self.handle = new

        def command(self, cdb, data_in=0, allow_check=False):
            req = SptBuffer()
            # VirtualAlloc is page-aligned, satisfying typical adapter alignment.
            data = None
            if data_in:
                k.VirtualAlloc.argtypes = [C.c_void_p, C.c_size_t, W.DWORD, W.DWORD]
                k.VirtualAlloc.restype = C.c_void_p
                k.VirtualFree.argtypes = [C.c_void_p, C.c_size_t, W.DWORD]
                data = k.VirtualAlloc(None, data_in, 0x3000, 4)
                if not data: raise C.WinError(C.get_last_error())
            try:
                req.spt.Length = C.sizeof(Spt)
                req.spt.CdbLength = len(cdb)
                req.spt.SenseInfoLength = 32
                req.spt.SenseInfoOffset = SptBuffer.sense.offset
                req.spt.DataIn = 1 if data_in else 2
                req.spt.DataTransferLength = data_in
                req.spt.TimeOutValue = 10
                req.spt.DataBuffer = data
                req.spt.Cdb[:len(cdb)] = cdb
                try:
                    ioctl(self.handle, 0x4d014, req, req)
                except OSError:
                    if not allow_check: raise
                    return b''
                if req.spt.ScsiStatus and not allow_check:
                    raise TransportError(f'SCSI status 0x{req.spt.ScsiStatus:02x}, sense {bytes(req.sense).hex()}')
                if data_in and req.spt.DataTransferLength != data_in:
                    raise TransportError('Short SCSI transfer')
                return C.string_at(data, data_in) if data_in else b''
            finally:
                if data: k.VirtualFree(data, 0, 0x8000)

        def lock_and_dismount(self):
            import time
            deadline = time.monotonic() + 8
            while True:
                try:
                    ioctl(self.handle, 0x90018)  # flushes cached data
                    break
                except OSError as exc:
                    if getattr(exc, 'winerror', None) not in (5, 32) or time.monotonic() >= deadline:
                        raise
                    time.sleep(.25)
            try:
                ioctl(self.handle, 0x90020)  # FSCTL_DISMOUNT_VOLUME
            except Exception:
                ioctl(self.handle, 0x9001c)
                raise

        def unlock(self):
            ioctl(self.handle, 0x9001c)

        def media_present(self):
            try:
                ioctl(self.handle, 0x2d0800)  # IOCTL_STORAGE_CHECK_VERIFY2
                return True
            except OSError as exc:
                if getattr(exc, 'winerror', None) in (21, 1112):
                    return False
                raise

elif sys.platform.startswith('linux'):
    import fcntl
    import glob
    import pathlib

    class SgIo(C.Structure):
        _fields_ = [('interface_id', C.c_int), ('dxfer_direction', C.c_int),
                    ('cmd_len', C.c_ubyte), ('mx_sb_len', C.c_ubyte), ('iovec_count', C.c_ushort),
                    ('dxfer_len', C.c_uint), ('dxferp', C.c_void_p), ('cmdp', C.c_void_p),
                    ('sbp', C.c_void_p), ('timeout', C.c_uint), ('flags', C.c_uint),
                    ('pack_id', C.c_int), ('usr_ptr', C.c_void_p), ('status', C.c_ubyte),
                    ('masked_status', C.c_ubyte), ('msg_status', C.c_ubyte), ('sb_len_wr', C.c_ubyte),
                    ('host_status', C.c_ushort), ('driver_status', C.c_ushort), ('resid', C.c_int),
                    ('duration', C.c_uint), ('info', C.c_uint)]

    def discover():
        return [{'path': p, 'vendor': 'Apple', 'product': 'iPod'} for p in
                glob.glob('/dev/disk/by-id/usb-Apple_iPod_*-0:0') if pathlib.Path(p).exists()]

    class LinuxTransport:
        def __init__(self, path):
            self.path = path
            self.fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)

        def close(self):
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None

        def command(self, cdb, data_in=0, allow_check=False):
            cmd = (C.c_ubyte * len(cdb)).from_buffer_copy(cdb)
            data = (C.c_ubyte * data_in)()
            sense = (C.c_ubyte * 32)()
            req = SgIo(interface_id=ord('S'), dxfer_direction=-3 if data_in else -1,
                       cmd_len=len(cdb), mx_sb_len=32, dxfer_len=data_in,
                       dxferp=C.addressof(data) if data_in else None, cmdp=C.addressof(cmd),
                       sbp=C.addressof(sense), timeout=10000)
            fcntl.ioctl(self.fd, 0x2285, req)
            if not allow_check and (req.status or req.host_status or req.driver_status or req.resid):
                raise TransportError(f'SCSI status={req.status}, host={req.host_status}, driver={req.driver_status}, resid={req.resid}')
            return bytes(data)

else:
    def discover():
        raise TransportError(f'No native SCSI backend for {sys.platform}; macOS support is not implemented')


def open_transport(path):
    if sys.platform == 'win32': return WindowsTransport(path)
    if sys.platform.startswith('linux'): return LinuxTransport(path)
    raise TransportError(f'Unsupported platform {sys.platform}')
