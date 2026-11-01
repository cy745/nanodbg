"""Exercise the real queued CLI while its stdin remains idle."""
import asyncio
import json
import subprocess
import sys

from experiments.ble.tap_host import tap


async def main():
    process = await asyncio.create_subprocess_exec(
        sys.executable, '-m', 'nanodbg', 'ble', 'interactive', '--probe', 'queued',
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))

    async def events(expected):
        while True:
            line = await asyncio.wait_for(process.stdout.readline(), 30)
            if not line:
                raise RuntimeError('CLI exited before ' + expected)
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            print(json.dumps(event), flush=True)
            if event.get('event') == expected:
                return event

    stderr_task = asyncio.create_task(process.stderr.read())
    try:
        await events('ready')
        for index, x in enumerate((60, 180), 1):
            await tap(x, 110)
            event = await events('device_notice')
            payload = bytes.fromhex(event['payload_hex'])
            if event['id'] != 0x7f + index or len(payload) != 6 or payload[4:] != bytes((index, index)):
                raise ValueError('idle notification mismatch')
        payload = bytes(range(40))
        process.stdin.write((payload.hex() + '\n').encode())
        await process.stdin.drain()
        event = await events('exchange')
        if event['echo_hex'] != payload.hex() or event['reversed_hex'] != payload[::-1].hex():
            raise ValueError('request mismatch')
        process.stdin.write(b'quit\n')
        await process.stdin.drain()
        await events('shutdown_acknowledged')
        if await asyncio.wait_for(process.wait(), 10):
            raise RuntimeError('CLI failed')
    finally:
        if process.returncode is None:
            process.terminate()
            await process.wait()
        stderr = await stderr_task
        if stderr:
            print(stderr.decode(errors='replace'), file=sys.stderr, end='')


if __name__ == '__main__':
    asyncio.run(main())
