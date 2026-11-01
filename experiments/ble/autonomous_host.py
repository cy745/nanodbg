"""Verify independently generated notices on btautonomousprobe, then shut it down."""
import asyncio
import json
import secrets

from nanodbg.ble_duplex import AdvertisementRadio, DuplexClient


async def main():
    async with AdvertisementRadio(20) as radio:
        client = DuplexClient(radio)
        startup = await client.start()
        print(json.dumps({'event': 'startup', 'payload_hex': startup.hex()}), flush=True)
        for index, length in ((1, 40), (2, 100)):
            payload = await client._notice(0x7f + index)
            if (len(payload) != length or payload[4] != index or
                    payload[5:] != bytes((i*7+index)&255 for i in range(5, length))):
                raise ValueError('invalid autonomous notice')
            print(json.dumps({'event': 'autonomous_notice', 'index': index,
                              'device_tick': int.from_bytes(payload[:4], 'little'),
                              'payload_hex': payload.hex()}), flush=True)
        tag = secrets.token_bytes(2)
        await radio.exchange(b'\xb4'+tag, lambda data: data == b'\xb5'+tag)
        await asyncio.sleep(4)
        print(json.dumps({'event': 'shutdown_acknowledged', 'cleanup_wait_seconds': 4}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
