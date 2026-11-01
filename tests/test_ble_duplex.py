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


class AutonomousRadio(FakeRadio):
    def __init__(self):
        super().__init__()
        self.notices = {0x80: bytes(range(40)), 0x81: bytes(range(100))}
        self.index = 0

    async def receive(self, accept):
        if self.index == 0:
            self.index += 1
            return await super().receive(accept)
        number = 0x7f + self.index
        self.index += 1
        payload = self.notices[number]
        packet = bytes((0xb0, number, 0, (len(payload)+18)//19)) + payload[:19]
        assert accept(packet)
        return packet

    async def exchange(self, data, accept):
        if data[0] == 0xb1 and data[1] in self.notices:
            payload = self.notices[data[1]]
            count = (len(payload)+18)//19
            seq = data[2]+1
            packet = (bytes((0xb2, data[1], count)) if seq == count else
                      bytes((0xb0, data[1], seq, count)) + payload[seq*19:(seq+1)*19])
            assert accept(packet)
            return packet
        if data[0] == 0xb4:
            self.shutdown_seen = True
            packet = b'\xb5'+data[1:]
            assert accept(packet)
            return packet
        return await super().exchange(data, accept)


class ContentionRadio(FakeRadio):
    def __init__(self):
        super().__init__()
        self.pending = [0x80, 0x81]
        self.interruptions = 0

    async def exchange(self, data, accept):
        if data[0] == 0xb1 and data[1] in self.pending:
            number = self.pending.pop(0)
            packet = bytes((0xb2, number, 1))
            assert accept(packet)
            return packet
        if data[0] in (0xa1, 0xb4) and self.pending:
            self.interruptions += 1
            packet = bytes((0xb0, self.pending[0], 0, 1, self.pending[0]))
            assert accept(packet)
            return packet
        if data[0] == 0xb4:
            self.shutdown_seen = True
            packet = b'\xb5' + data[1:]
            assert accept(packet)
            return packet
        return await super().exchange(data, accept)


class DuplexTests(unittest.IsolatedAsyncioTestCase):
    async def test_queued_notices_interrupt_and_resume_request(self):
        radio = ContentionRadio()
        client = DuplexClient(radio, queue_notices=True)
        await client.start()
        result = await client.request(b'hello')
        self.assertEqual(result['echo_hex'], b'hello'.hex())
        self.assertEqual(client.pop_notices(), [(0x80, b'\x80'), (0x81, b'\x81')])
        self.assertEqual(client.pop_notices(), [])
        self.assertEqual(radio.interruptions, 2)
        await client.shutdown()

    async def test_queued_shutdown_and_identifier_limit(self):
        radio = ContentionRadio()
        client = DuplexClient(radio, queue_notices=True)
        await client.start()
        client.round = 127
        with self.assertRaises(ValueError):
            await client.request(b'one')
        self.assertEqual(client.state, 'ready')
        client.round = 0
        await client.shutdown_queued()
        self.assertEqual(len(client.pop_notices()), 2)
        self.assertTrue(radio.shutdown_seen)

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

    async def test_autonomous_notices_followed_by_request(self):
        radio = AutonomousRadio()
        client = DuplexClient(radio)
        await client.start()
        for ident in (0x80, 0x81):
            self.assertEqual(await client.receive_notice(ident), radio.notices[ident])
        result = await client.request(b'after notices')
        self.assertEqual(result['echo_hex'], b'after notices'.hex())
        await client.shutdown()
        self.assertTrue(radio.shutdown_seen)

    async def test_autonomous_shutdown_without_request(self):
        radio = AutonomousRadio()
        client = DuplexClient(radio)
        await client.start()
        await client.receive_notice(0x80)
        await client.receive_notice(0x81)
        await client.shutdown_autonomous()
        self.assertEqual(client.state, 'closed')
        self.assertTrue(radio.shutdown_seen)
