"""Cause queued touch notices to compete with the first host request."""
import asyncio
import json

from experiments.ble.tap_host import tap
from nanodbg.ble_duplex import AdvertisementRadio, DuplexClient


async def main():
    async with AdvertisementRadio(20) as radio:
        client = DuplexClient(radio, queue_notices=True)
        startup = await client.start()
        print(json.dumps({'event': 'startup', 'payload_hex': startup.hex()}), flush=True)
        await tap(60, 110)
        await tap(180, 110)
        print(json.dumps(await client.request(bytes(range(40)))), flush=True)
        notices = client.pop_notices()
        if len(notices) != 2:
            raise ValueError('expected two notices during request')
        for index, (number, payload) in enumerate(notices, 1):
            if number != 0x7f + index or len(payload) != 6 or payload[4:] != bytes((index, index)):
                raise ValueError('event data or order mismatch')
            print(json.dumps({'event': 'queued_notice', 'id': number,
                              'payload_hex': payload.hex()}), flush=True)
        await client.shutdown()
        await asyncio.sleep(4)
        print(json.dumps({'event': 'shutdown_acknowledged', 'cleanup_wait_seconds': 4}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
