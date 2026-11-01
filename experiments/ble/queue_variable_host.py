"""Verify device-generated 40- and 216-byte notices and a host request."""
import asyncio
import json

from experiments.ble.tap_host import tap
from nanodbg.ble_duplex import AdvertisementRadio, DuplexClient


async def main():
    async with AdvertisementRadio(20) as radio:
        client = DuplexClient(radio, queue_notices=True)
        startup = await client.start()
        print(json.dumps({'event': 'startup', 'payload_hex': startup.hex()}), flush=True)
        for index, (x, length) in enumerate(((60, 40), (180, 216)), 1):
            await tap(x, 110)
            payload = await client.receive_notice(0x7f + index)
            if len(payload) != length or payload[4:6] != bytes((index, index)):
                raise ValueError('notice header or length mismatch')
            tick = int.from_bytes(payload[:4], 'little')
            expected = bytes((tick + i * 37 + index * 11) & 255 for i in range(6, length))
            if payload[6:] != expected:
                raise ValueError('device-generated payload mismatch')
            print(json.dumps({'event': 'device_notice', 'id': 0x7f + index,
                              'length': length, 'payload_hex': payload.hex()}), flush=True)
        request = bytes(range(40))
        result = await client.request(request)
        print(json.dumps(result), flush=True)
        await client.shutdown()
        await asyncio.sleep(4)
        print(json.dumps({'event': 'shutdown_acknowledged', 'cleanup_wait_seconds': 4}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
