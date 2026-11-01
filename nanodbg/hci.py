"""Experimental file-based HCI probe protocol and result validation."""
import re


def encode_request(opcode, params, nonce):
    if not 0 <= opcode <= 0xffff or len(params) > 255 or len(nonce) != 4:
        raise ValueError('invalid opcode, parameter length, or nonce')
    return b'HCP1' + nonce + opcode.to_bytes(2, 'little') + bytes((len(params),)) + params


def parse_result(raw, request):
    try:
        text = raw.rstrip(b'\0').decode('ascii')
        match = re.fullmatch(
            r'hci-request-v1\r?\nnonce ((?:[0-9a-f]{2} ){4})opcode ((?:[0-9a-f]{2} ){2})'
            r'params ((?:[0-9a-f]{2} )*)\r?\nrc ([0-9a-f]{2}) status ([0-9a-f]{2}) '
            r'data ((?:[0-9a-f]{2} )*)\r?\n', text)
        if not match:
            raise ValueError('malformed HCI result')
        nonce, opcode, params, rc, status, data = match.groups()
        if (bytes.fromhex(nonce) != request[4:8] or bytes.fromhex(opcode) != request[8:10]
                or bytes.fromhex(params) != request[11:]):
            raise ValueError('HCI result does not match request')
        rc = int(rc, 16)
        return {'nonce': request[4:8].hex(), 'opcode': int.from_bytes(request[8:10], 'little'),
                'params_hex': request[11:].hex(), 'rc': rc-256 if rc >= 128 else rc,
                'controller_status': int(status, 16), 'data_hex': bytes.fromhex(data).hex()}
    except (UnicodeError, IndexError) as exc:
        raise ValueError('malformed HCI result') from exc
