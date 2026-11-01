"""Exercise bounded device event queue while withholding all notice ACKs."""
import asyncio
import json
from experiments.ble.tap_host import tap
from nanodbg.ble_duplex import AdvertisementRadio, DuplexClient


async def main():
    async with AdvertisementRadio(20) as radio:
        client = DuplexClient(radio)
        startup = await client.start()
        print(json.dumps({'event': 'startup', 'payload_hex': startup.hex()}), flush=True)
        buttons = (1, 2, 1, 2, 1, 2)
        for button in buttons:
            await tap(60 if button == 1 else 180, 110)
        print(json.dumps({'event': 'injections_complete', 'count': len(buttons)}), flush=True)
        for index, button in enumerate(buttons[:5], 1):
            payload = await client.receive_notice(0x7f+index)
            if len(payload) != 6 or payload[4:] != bytes((button, index)):
                raise ValueError('device queue order or event data mismatch')
            print(json.dumps({'event': 'queued_notice', 'button': button, 'count': index,
                              'tick': int.from_bytes(payload[:4], 'little')}), flush=True)
        print(json.dumps(await client.request(bytes.fromhex('00ff1234567890'))), flush=True)
        await client.shutdown()
        await asyncio.sleep(4)
        print(json.dumps({'event': 'shutdown_acknowledged', 'cleanup_wait_seconds': 4}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
