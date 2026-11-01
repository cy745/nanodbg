"""Exercise runtime touch-driven device messages and an intervening host request."""
import asyncio
import json
import subprocess
import sys

from nanodbg.ble_duplex import AdvertisementRadio, DuplexClient


async def tap(x, y):
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'nanodbg', 'tap', str(x), str(y),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    stdout, stderr = await process.communicate()
    if process.returncode:
        raise RuntimeError('tap failed: ' + stderr.decode(errors='replace'))
    print(json.dumps({'event': 'tap_injected', 'output': stdout.decode(errors='replace').strip()}), flush=True)


async def main():
    async with AdvertisementRadio(20) as radio:
        client = DuplexClient(radio)
        startup = await client.start()
        print(json.dumps({'event': 'startup', 'payload_hex': startup.hex()}), flush=True)
        for index, (x, button) in enumerate(((60, 1), (180, 2)), 1):
            await tap(x, 110)
            payload = await client.receive_notice(0x7f + index)
            if len(payload) != 6 or payload[4:] != bytes((button, index)):
                raise ValueError('unexpected tap message')
            print(json.dumps({'event': 'tap_notice', 'button': button, 'count': index,
                              'tick': int.from_bytes(payload[:4], 'little'),
                              'payload_hex': payload.hex()}), flush=True)
            if index == 1:
                print(json.dumps(await client.request(bytes.fromhex('00ff1234567890'))), flush=True)
        await client.shutdown()
        await asyncio.sleep(4)
        print(json.dumps({'event': 'shutdown_acknowledged', 'cleanup_wait_seconds': 4}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
