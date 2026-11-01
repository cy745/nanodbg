import unittest
from experiments.ble.hci_request import encode_request
from nanodbg.hci import parse_result


class HciRequestTests(unittest.TestCase):
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
        with self.assertRaises(ValueError):
            parse_result(raw, encode_request(0x1405, b'\xff\x0f', b'xxxx'))
        with self.assertRaises(ValueError):
            parse_result(raw[:-3], request)


if __name__ == '__main__':
    unittest.main()
