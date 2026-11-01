import unittest
from experiments.ble.hci_request import encode_request
from nanodbg.hci import decode_extended_inquiry, parse_result


class HciRequestTests(unittest.TestCase):
    def test_extended_inquiry_fixed_header(self):
        payload = bytes.fromhex('01080a8f21129c010010010a9203ce0000')
        result = decode_extended_inquiry(payload, 255)
        self.assertEqual(result['address'], '9C:12:21:8F:0A:08')
        self.assertEqual(result['class_of_device'], '0A0110')
        self.assertEqual(result['clock_offset'], 0x0392)
        self.assertEqual(result['rssi_dbm'], -50)
        self.assertEqual(result['eir_prefix_hex'], '0000')
        self.assertIsNone(decode_extended_inquiry(payload, 254))
        self.assertIsNone(decode_extended_inquiry(payload[:14], 255))
        self.assertIsNone(decode_extended_inquiry(b'\x02' + payload[1:], 255))

    def test_parameterized_and_empty_commands(self):
        self.assertEqual(encode_request(0x200b, bytes.fromhex('00600030000000'), b'abcd'),
                         b'HCP1abcd\x0b\x20\x07\x00\x60\x00\x30\x00\x00\x00')
        self.assertEqual(encode_request(0x1001, b'', b'1234'), b'HCP11234\x01\x10\x00')
        self.assertEqual(len(encode_request(0xffff, bytes(255), b'abcd')), 266)

    def test_bounds(self):
        for opcode, data, nonce in ((-1,b'',b'abcd'), (65536,b'',b'abcd'),
                                    (1,bytes(256),b'abcd'), (1,b'',b'bad')):
            with self.subTest(opcode=opcode, length=len(data), nonce=nonce):
                with self.assertRaises(ValueError):
                    encode_request(opcode, data, nonce)

    def test_result_requires_matching_request_and_complete_record(self):
        request = encode_request(0x1405, b'\xff\x0f', b'abcd')
        raw = (b'hci-request-v1\nnonce 61 62 63 64 opcode 05 14 params ff 0f \n'
               b'rc fc status 12 data \n\0')
        result = parse_result(raw, request)
        self.assertEqual((result['rc'], result['controller_status']), (-4, 0x12))
        self.assertIsNone(result['response_event'])
        with_event = raw.replace(b'status 12 data', b'status 12 event 0f data')
        self.assertEqual(parse_result(with_event, request)['response_event'], 0x0f)
        capture = with_event[:-1] + b'inquiry-complete 00 hook restored\n\0'
        self.assertEqual(parse_result(capture, request)['inquiry_complete_status'], 0)
        self.assertEqual(parse_result(capture, request)['inquiry_hook'], 'restored')
        no_capture = with_event[:-1] + b'inquiry-complete none hook changed\n\0'
        self.assertIsNone(parse_result(no_capture, request)['inquiry_complete_status'])
        self.assertEqual(parse_result(no_capture, request)['inquiry_hook'], 'changed')
        records = (capture[:-1] + b'inquiry-result 22 04 01 02 03 04 \n'
                   b'inquiry-dropped 01 \n\0')
        parsed = parse_result(records, request)
        self.assertEqual(parsed['inquiry_results'][0]['payload_hex'], '01020304')
        self.assertEqual(parsed['inquiry_dropped'], 1)
        with self.assertRaises(ValueError):
            parse_result(records.replace(b'04 01 02 03 04', b'05 01 02 03 04'), request)
        with self.assertRaises(ValueError):
            parse_result(raw, encode_request(0x1405, b'\xff\x0f', b'xxxx'))
        with self.assertRaises(ValueError):
            parse_result(raw[:-3], request)


if __name__ == '__main__':
    unittest.main()
