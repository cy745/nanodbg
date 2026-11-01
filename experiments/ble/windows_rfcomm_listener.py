"""Minimal Windows RFCOMM listener for classic Bluetooth experiments.

The socket reserves an automatically chosen RFCOMM channel but does not
advertise it through SDP. No authentication option is explicitly requested.
"""
import ctypes
import socket
import sys


class _Guid(ctypes.Structure):
    _fields_ = [('data1', ctypes.c_uint32), ('data2', ctypes.c_uint16),
                ('data3', ctypes.c_uint16), ('data4', ctypes.c_ubyte * 8)]


class _SockaddrBth(ctypes.Structure):
    _pack_ = 1  # ws2bth.h uses one-byte packing
    _fields_ = [('family', ctypes.c_uint16), ('address', ctypes.c_uint64),
                ('service', _Guid), ('port', ctypes.c_uint32)]


def listen():
    """Return (socket, assigned channel); the caller owns and closes it."""
    if sys.platform != 'win32':
        raise OSError('Windows Bluetooth sockets are required')
    ws = ctypes.WinDLL('Ws2_32.dll')
    ws.bind.argtypes = [ctypes.c_size_t, ctypes.POINTER(_SockaddrBth), ctypes.c_int]
    ws.bind.restype = ctypes.c_int
    ws.getsockname.argtypes = [ctypes.c_size_t, ctypes.POINTER(_SockaddrBth),
                               ctypes.POINTER(ctypes.c_int)]
    ws.getsockname.restype = ctypes.c_int
    ws.WSAGetLastError.restype = ctypes.c_int
    sock = socket.socket(32, socket.SOCK_STREAM, 3)  # AF_BTH, BTHPROTO_RFCOMM
    try:
        addr = _SockaddrBth()
        addr.family, addr.port = 32, 0xffffffff  # AF_BTH, BT_PORT_ANY
        if ws.bind(sock.fileno(), ctypes.byref(addr), ctypes.sizeof(addr)):
            raise OSError(ws.WSAGetLastError(), 'Bluetooth bind failed')
        size = ctypes.c_int(ctypes.sizeof(addr))
        if ws.getsockname(sock.fileno(), ctypes.byref(addr), ctypes.byref(size)):
            raise OSError(ws.WSAGetLastError(), 'Bluetooth getsockname failed')
        if size.value != ctypes.sizeof(addr) or not 1 <= addr.port <= 30:
            raise OSError('Invalid RFCOMM listener address')
        sock.listen(1)
        return sock, addr.port
    except BaseException:
        sock.close()
        raise
