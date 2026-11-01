import asyncio, json
from bleak import BleakScanner
from nanodbg.ble import advertise, COMPANY_ID

async def main():
    values = [bytes.fromhex(s) for s in ('0100ff112233', '02deadbeef00', '030080aabbcc', '04ffee001122')]
    expected = None
    matched = asyncio.Event()
    def callback(device, adv):
        if expected is not None and adv.manufacturer_data.get(COMPANY_ID) == expected:
            matched.set()
    async with BleakScanner(detection_callback=callback):
        for value in values:
            expected = value
            matched.clear()
            task = asyncio.create_task(advertise(value, 12))
            try:
                await asyncio.wait_for(matched.wait(), 12)
                print(json.dumps({'received': value.hex()}), flush=True)
            finally:
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass
            await asyncio.sleep(.8)
    print('all complete', flush=True)
asyncio.run(main())
