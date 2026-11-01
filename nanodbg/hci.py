"""Experimental file-based HCI probe protocol and result validation."""
import re


def decode_extended_inquiry(payload, length):
    """Decode the fixed header of a standard Extended Inquiry Result."""
    if length != 255 or len(payload) < 15 or payload[0] != 1:
        return None
    rssi = payload[14]
    return {'address': ':'.join(f'{b:02X}' for b in reversed(payload[1:7])),
            'page_scan_repetition_mode': payload[7],
            'class_of_device': f'{int.from_bytes(payload[9:12], "little"):06X}',
            'clock_offset': int.from_bytes(payload[12:14], 'little'),
            'rssi_dbm': rssi - 256 if rssi >= 128 else rssi,
            'eir_prefix_hex': payload[15:].hex()}


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
            r'(?:event ([0-9a-f]{2}) )?data ((?:[0-9a-f]{2} )*)\r?\n'
            r'(?:inquiry-complete (none|[0-9a-f]{2}) hook (restored|changed)\r?\n'
            r'((?:inquiry-result [0-9a-f]{2} [0-9a-f]{2} (?:[0-9a-f]{2} )*\r?\n)*)'
            r'(?:inquiry-dropped ([0-9a-f]{2}) \r?\n)?)?'
            r'(?:connection-complete (none |(?:[0-9a-f]{2} ){11})hook (restored|changed)\r?\n'
            r'(?:connection-cleanup ((?:[0-9a-f]{2} ){5})\r?\n)?)?', text)
        if not match:
            raise ValueError('malformed HCI result')
        (nonce, opcode, params, rc, status, event, data, inquiry, hook, records, dropped,
         connection, connection_hook, cleanup) = match.groups()
        if (bytes.fromhex(nonce) != request[4:8] or bytes.fromhex(opcode) != request[8:10]
                or bytes.fromhex(params) != request[11:]):
            raise ValueError('HCI result does not match request')
        rc = int(rc, 16)
        if records and dropped is None:
            raise ValueError('incomplete inquiry result capture')
        results = []
        for line in (records or '').splitlines():
            fields = line.split()
            code, length = int(fields[1], 16), int(fields[2], 16)
            payload = bytes.fromhex(' '.join(fields[3:]))
            if code not in (2, 0x22, 0x2f) or len(payload) != min(length, 32):
                raise ValueError('malformed inquiry result record')
            record = {'event': code, 'length': length,
                      'payload_hex': payload.hex(), 'truncated': len(payload) < length}
            if code == 0x2f:
                record['extended'] = decode_extended_inquiry(payload, length)
            results.append(record)
        if len(results) > 6:
            raise ValueError('too many inquiry result records')
        connection_data = None if not connection or connection == 'none ' else bytes.fromhex(connection)
        if connection is not None and (request[8:10] != b'\x05\x04' or len(request[11:]) != 13):
            raise ValueError('unexpected connection capture')
        if connection_data is not None and (request[8:10] != b'\x05\x04' or
                                             len(request[11:]) != 13 or
                                             connection_data[3:9] != request[11:17]):
            raise ValueError('connection event does not match target')
        cleanup_data = bytes.fromhex(cleanup) if cleanup else None
        connection_info = None
        if connection_data is not None:
            connection_info = {'status': connection_data[0],
                               'handle': (int.from_bytes(connection_data[1:3], 'little') & 0x0fff)
                               if connection_data[0] == 0 else None,
                               'address': ':'.join(f'{b:02X}' for b in reversed(connection_data[3:9])),
                               'link_type': connection_data[9] if connection_data[0] == 0 else None,
                               'encryption_enabled': connection_data[10] if connection_data[0] == 0 else None}
        return {'nonce': request[4:8].hex(), 'opcode': int.from_bytes(request[8:10], 'little'),
                'params_hex': request[11:].hex(), 'rc': rc-256 if rc >= 128 else rc,
                'controller_status': int(status, 16),
                'response_event': int(event, 16) if event is not None else None,
                'data_hex': bytes.fromhex(data).hex(),
                'inquiry_complete_status': int(inquiry, 16) if inquiry and inquiry != 'none' else None,
                'inquiry_hook': hook, 'inquiry_results': results,
                'inquiry_dropped': int(dropped, 16) if dropped is not None else None,
                'connection_complete_hex': connection_data.hex() if connection_data else None,
                'connection_complete': connection_info,
                'connection_hook': connection_hook,
                'connection_cleanup_hex': cleanup_data.hex() if cleanup_data else None}
    except (UnicodeError, IndexError) as exc:
        raise ValueError('malformed HCI result') from exc
