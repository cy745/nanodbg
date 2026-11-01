"""Verify the reusable device inbox at its full 216-byte limit."""
import asyncio
import json
from nanodbg.ble_duplex import AdvertisementRadio, DuplexClient


async def main():
    async with AdvertisementRadio(20) as radio:
        client = DuplexClient(radio, queue_notices=True)
        startup = await client.start()
        print(json.dumps({'event': 'startup', 'payload_hex': startup.hex()}), flush=True)
        payload = bytes((i * 37 + 11) & 255 for i in range(216))
        result = await client.request(payload)
        if result['echo_hex'] != payload.hex() or result['reversed_hex'] != payload[::-1].hex():
            raise ValueError('device inbox contents differ from request')
        print(json.dumps(result), flush=True)
        await client.shutdown()
        await asyncio.sleep(4)
        print(json.dumps({'event': 'shutdown_acknowledged', 'cleanup_wait_seconds': 4}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
