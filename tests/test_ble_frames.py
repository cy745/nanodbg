import unittest
from experiments.ble.framed_host import frames

class FrameTests(unittest.TestCase):
    def test_roundtrip_boundaries(self):
        for length in (1, 18, 19, 95, 216):
            with self.subTest(length=length):
                original = bytes(i % 256 for i in range(length))
                packets = frames(original, b'\x01\x02')
                self.assertEqual(b''.join(packet[5:] for packet in packets), original)
                self.assertEqual([p[3] for p in packets], list(range(len(packets))))
                self.assertTrue(all(p[:3] == b'\xa1\x01\x02' and p[4] == len(packets) and len(p) <= 23 for p in packets))

    def test_invalid_inputs(self):
        for message, session in ((b'', b'12'), (bytes(217), b'12'), (b'a', b'1')):
            with self.subTest(length=len(message), session=session):
                with self.assertRaises(ValueError): frames(message, session)

if __name__ == '__main__': unittest.main()
