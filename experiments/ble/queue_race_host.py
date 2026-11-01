"""Inject device events mid-request and verify queue retry after synthetic failure."""
import asyncio
import json
from experiments.ble.tap_host import tap
from nanodbg.ble_duplex import AdvertisementRadio, DuplexClient


class InjectDuringRequest:
    def __init__(self, radio):
        self.radio = radio
        self.injected = False

    async def receive(self, accept):
        return await self.radio.receive(accept)

    async def exchange(self, data, accept):
        response = await self.radio.exchange(data, accept)
        if data[0] == 0xa1 and data[3] == 0 and not self.injected:
            self.injected = True
            print(json.dumps({'event': 'request_first_fragment_acknowledged'}), flush=True)
            await tap(60, 110)
            await tap(180, 110)
            print(json.dumps({'event': 'mid_request_taps_injected'}), flush=True)
        return response


async def main():
    async with AdvertisementRadio(20) as radio:
        client = DuplexClient(InjectDuringRequest(radio))
        startup = await client.start()
        print(json.dumps({'event': 'startup', 'payload_hex': startup.hex()}), flush=True)
        request = bytes(range(40))
        print(json.dumps(await client.request(request)), flush=True)
        for index in (1, 2):
            payload = await client.receive_notice(0x7f+index)
            if len(payload) != 6 or payload[4:] != bytes((index, index)):
                raise ValueError('event data or order mismatch')
            print(json.dumps({'event': 'queued_notice', 'button': index,
                              'tick': int.from_bytes(payload[:4], 'little')}), flush=True)
        await client.shutdown()
        await asyncio.sleep(4)
        print(json.dumps({'event': 'shutdown_acknowledged', 'cleanup_wait_seconds': 4}), flush=True)


if __name__ == '__main__':
    asyncio.run(main())
