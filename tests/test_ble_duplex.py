import unittest
from nanodbg.ble_duplex import DuplexClient


class FakeRadio:
    def __init__(self, corrupt=False):
        self.payload = bytearray()
        self.corrupt = corrupt
        self.round = 0
        self.sessions = []
        self.shutdown_seen = False

    async def receive(self, accept):
        packet = b'\xb0\x00\x00\x01\x01\x02\x03\x04\x00'
        assert accept(packet)
        return packet

    async def exchange(self, data, accept):
        op = data[0]
        if op == 0xb1:
            seq = data[2]
            if data[1] == 0:
                packet = b'\xb2\x00\x01'
            else:
                count = (len(self.payload)+18)//19
                if seq+1 == count:
                    packet = bytes((0xb2, self.round, count))
                else:
                    packet = bytes((0xb0, self.round, seq+1, count)) + self.payload[(seq+1)*19:(seq+2)*19]
        elif op == 0xa1:
            if data[3] == 0:
                self.payload.clear()
                self.sessions.append(data[1:3])
            self.payload.extend(data[5:])
            packet = data
        elif op in (0xa4, 0xa3):
            seq = 0 if op == 0xa4 else data[3]+1
            count = (len(self.payload)+17)//18
            if seq == count:
                packet = b'\xa5' + data[1:3]
            else:
                reply = bytes(self.payload)[::-1]
                if self.corrupt:
                    reply = b'\xff' * len(reply)
                packet = b'\xa2' + data[1:3] + bytes((seq, count)) + reply[seq*18:(seq+1)*18]
        elif op == 0xb3:
            self.round += 1
            count = (len(self.payload)+18)//19
            packet = bytes((0xb0, self.round, 0, count)) + self.payload[:19]
        elif op == 0xa6:
            self.shutdown_seen = True
            packet = b'\xa7' + data[1:3]
        else:
            raise AssertionError(data.hex())
        assert accept(packet), packet.hex()
        return packet


class DuplexTests(unittest.IsolatedAsyncioTestCase):
    async def test_multiple_requests_and_shutdown(self):
        radio = FakeRadio()
        client = DuplexClient(radio)
        self.assertEqual(await client.start(), b'\x01\x02\x03\x04\x00')
        for payload in (b'\0', bytes(range(20)), bytes(range(216))):
            result = await client.request(payload)
            self.assertEqual(result['echo_hex'], payload.hex())
            self.assertEqual(result['reversed_hex'], payload[::-1].hex())
        self.assertEqual(len(set(radio.sessions)), 3)
        await client.shutdown()
        self.assertTrue(radio.shutdown_seen)
        self.assertEqual(client.state, 'closed')

    async def test_validation_does_not_damage_session(self):
        client = DuplexClient(FakeRadio())
        await client.start()
        for payload in (b'', bytes(217)):
            with self.assertRaises(ValueError):
                await client.request(payload)
        self.assertEqual(client.state, 'ready')
        with self.assertRaises(ValueError):
            await client.shutdown()
        self.assertEqual(client.state, 'ready')

    async def test_failed_exchange_disables_reuse(self):
        client = DuplexClient(FakeRadio(corrupt=True))
        await client.start()
        with self.assertRaisesRegex(ValueError, 'reply mismatch'):
            await client.request(b'hello')
        self.assertEqual(client.state, 'failed')
        with self.assertRaises(ValueError):
            await client.request(b'hello')
        with self.assertRaises(ValueError):
            await client.shutdown()
