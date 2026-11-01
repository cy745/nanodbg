"""Interactive client for the experimental runtime-outbox BLE probe.

This is an unauthenticated advertisement protocol, not a general BLE connection.
"""
import asyncio
import json
import secrets
import sys

from .ble import COMPANY_ID, advertise, parse_payload


class AdvertisementRadio:
    def __init__(self, timeout):
        self.timeout = timeout
        self.queue = asyncio.Queue(maxsize=1024)

    async def __aenter__(self):
        try:
            from bleak import BleakScanner
        except ImportError as exc:
            raise ValueError('BLE scanning requires the optional bleak dependency') from exc
        def callback(_device, advertisement):
            data = advertisement.manufacturer_data.get(COMPANY_ID)
            if data:
                if self.queue.full():
                    self.queue.get_nowait()
                self.queue.put_nowait(data)
        self.scanner = BleakScanner(detection_callback=callback)
        await self.scanner.start()
        return self

    async def __aexit__(self, *_):
        await self.scanner.stop()

    async def receive(self, accept):
        async def find():
            while True:
                data = await self.queue.get()
                if accept(data):
                    return data
        return await asyncio.wait_for(find(), self.timeout)

    async def exchange(self, data, accept):
        sender = asyncio.create_task(advertise(data, self.timeout))
        receiver = asyncio.create_task(self.receive(accept))
        try:
            done, _ = await asyncio.wait((sender, receiver), return_when=asyncio.FIRST_COMPLETED)
            if sender in done:
                await sender
                raise TimeoutError('advertising ended before a response arrived')
            return await receiver
        finally:
            for task in (sender, receiver):
                if not task.done():
                    task.cancel()
            await asyncio.gather(sender, receiver, return_exceptions=True)


class DuplexClient:
    """One sequential session with the specific runtime-outbox echo firmware."""
    def __init__(self, radio):
        self.radio = radio
        self.state = 'new'
        self.round = 0
        self.sessions = set()
        self.last_session = None
        self.notices_received = set()

    async def _notice(self, number, packet=None):
        if packet is None:
            packet = await self.radio.receive(lambda d: len(d) >= 5 and d[:3] == bytes((0xb0, number, 0)))
        total = packet[3]
        if not 1 <= total <= 12:
            raise ValueError('invalid outbox fragment count')
        payload = bytearray()
        for seq in range(total):
            if packet[:4] != bytes((0xb0, number, seq, total)) or not 1 <= len(packet[4:]) <= 19:
                raise ValueError('invalid outbox fragment')
            payload.extend(packet[4:])
            ack = bytes((0xb1, number, seq))
            if seq + 1 == total:
                await self.radio.exchange(ack, lambda d: d == bytes((0xb2, number, total)))
            else:
                packet = await self.radio.exchange(ack, lambda d, i=seq+1: len(d) >= 5 and d[:4] == bytes((0xb0, number, i, total)))
        return bytes(payload)

    async def start(self):
        if self.state != 'new':
            raise ValueError('client already started')
        self.state = 'busy'
        try:
            data = await self._notice(0)
            if len(data) != 5 or data[4] != 0:
                raise ValueError('invalid startup notice')
            self.state = 'ready'
            return data
        except BaseException:
            self.state = 'failed'
            raise

    async def receive_notice(self, number):
        """Receive an expected device-originated notice while no request is active."""
        if self.state != 'ready':
            raise ValueError('client is not ready')
        if not isinstance(number, int) or not 1 <= number <= 255:
            raise ValueError('notice identifier must be 1-255')
        self.state = 'busy'
        try:
            data = await self._notice(number)
            self.notices_received.add(number)
            self.state = 'ready'
            return data
        except BaseException:
            self.state = 'failed'
            raise

    async def request(self, payload):
        if self.state != 'ready':
            raise ValueError('client is not ready')
        if not isinstance(payload, bytes) or not 1 <= len(payload) <= 216:
            raise ValueError('request must contain 1-216 bytes')
        if self.round >= 255:
            raise ValueError('one boot supports at most 255 rounds')
        self.state = 'busy'
        try:
            session = secrets.token_bytes(2)
            while session in self.sessions:
                session = secrets.token_bytes(2)
            self.sessions.add(session)
            total = (len(payload) + 17) // 18
            for seq in range(total):
                frame = b'\xa1' + session + bytes((seq, total)) + payload[seq*18:(seq+1)*18]
                await self.radio.exchange(frame, lambda d, p=frame: d == p)
            packet = await self.radio.exchange(b'\xa4' + session, lambda d: len(d) >= 6 and d[:4] == b'\xa2' + session + b'\0')
            count = packet[4]
            if not 1 <= count <= 12:
                raise ValueError('invalid reply fragment count')
            reply = bytearray()
            for seq in range(count):
                if packet[:5] != b'\xa2' + session + bytes((seq, count)) or not 1 <= len(packet[5:]) <= 18:
                    raise ValueError('invalid reply fragment')
                reply.extend(packet[5:])
                ack = b'\xa3' + session + bytes((seq,))
                if seq + 1 == count:
                    await self.radio.exchange(ack, lambda d: d == b'\xa5' + session)
                else:
                    packet = await self.radio.exchange(ack, lambda d, i=seq+1: len(d) >= 6 and d[:4] == b'\xa2' + session + bytes((i,)))
            if reply != payload[::-1]:
                raise ValueError('device reply mismatch')
            number = self.round + 1
            first = await self.radio.exchange(b'\xb3' + session, lambda d: len(d) >= 5 and d[:3] == bytes((0xb0, number, 0)))
            echo = await self._notice(number, first)
            if echo != payload:
                raise ValueError('device outbox payload mismatch')
            self.round = number
            self.last_session = session
            self.state = 'ready'
            return {'event': 'exchange', 'round': number, 'session_hex': session.hex(),
                    'request_hex': payload.hex(), 'reversed_hex': reply.hex(), 'echo_hex': echo.hex()}
        except BaseException:
            self.state = 'failed'
            raise

    async def shutdown_autonomous(self):
        """Shutdown the autonomous probe after its two device notices."""
        if self.state != 'ready' or self.round or not {0x80, 0x81} <= self.notices_received:
            raise ValueError('autonomous shutdown requires both notices and no requests')
        self.state = 'busy'
        try:
            tag = secrets.token_bytes(2)
            await self.radio.exchange(b'\xb4' + tag, lambda d: d == b'\xb5' + tag)
            self.state = 'closed'
        except BaseException:
            self.state = 'failed'
            raise

    async def shutdown(self):
        if self.state != 'ready' or not self.last_session:
            raise ValueError('clean shutdown requires a completed request')
        self.state = 'busy'
        try:
            await self.radio.exchange(b'\xa6' + self.last_session, lambda d: d == b'\xa7' + self.last_session)
            self.state = 'closed'
        except BaseException:
            self.state = 'failed'
            raise


async def interactive(timeout, probe="runtime"):
    if timeout <= 0:
        raise ValueError('timeout must be positive')
    async with AdvertisementRadio(timeout) as radio:
        client = DuplexClient(radio)
        try:
            startup = await client.start()
            print(json.dumps({'event': 'ready', 'startup_payload_hex': startup.hex()}), flush=True)
            if probe == 'autonomous':
                for number in (0x80, 0x81):
                    payload = await client.receive_notice(number)
                    print(json.dumps({'event': 'device_notice', 'id': number,
                                      'payload_hex': payload.hex()}), flush=True)
            while True:
                if sys.stdin.isatty():
                    print('hex payload (or quit)> ', end='', file=sys.stderr, flush=True)
                line = await asyncio.to_thread(sys.stdin.readline)
                if not line or line.strip().lower() == 'quit':
                    break
                try:
                    payload = parse_payload(line.strip(), 216)
                except ValueError as exc:
                    print(str(exc), file=sys.stderr, flush=True)
                    continue
                print(json.dumps(await client.request(payload)), flush=True)
            if client.round:
                await client.shutdown()
                await asyncio.sleep(4)
                print(json.dumps({'event': 'shutdown_acknowledged', 'cleanup_wait_seconds': 4}), flush=True)
            elif probe == 'autonomous':
                await client.shutdown_autonomous()
                await asyncio.sleep(4)
                print(json.dumps({'event': 'shutdown_acknowledged', 'cleanup_wait_seconds': 4}), flush=True)
            else:
                print('No request completed; probe must exit via its watchdog or device reboot.', file=sys.stderr, flush=True)
        except BaseException:
            print('Session interrupted; probe cleanup is not confirmed. It has a finite watchdog.', file=sys.stderr, flush=True)
            raise


def run_interactive(timeout, probe="runtime"):
    asyncio.run(interactive(timeout, probe))
