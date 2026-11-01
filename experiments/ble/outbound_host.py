import asyncio, json
from nanodbg.ble import advertise, COMPANY_ID

async def main():
    from bleak import BleakScanner
    queue = asyncio.Queue()
    def callback(device, adv):
        data = adv.manufacturer_data.get(COMPANY_ID, b'')
        if len(data) >= 6 and data[:3] == b'\xa2N7': queue.put_nowait(data)
    ack_task = None
    message = bytearray()
    seq = 0
    total = None
    try:
        async with BleakScanner(detection_callback=callback):
            while total is None or seq < total:
                packet = await asyncio.wait_for(queue.get(), 15)
                number, count = packet[3:5]
                if not 1 <= count <= 12 or number != seq or (total is not None and count != total): continue
                total = count
                message.extend(packet[5:])
                print(json.dumps({'frame': number, 'payload': packet[5:].hex()}), flush=True)
                if ack_task:
                    ack_task.cancel()
                    try: await ack_task
                    except asyncio.CancelledError: pass
                ack_task = asyncio.create_task(advertise(b'\xa3N7' + bytes([number]), 20))
                seq += 1
            await asyncio.sleep(4)
        print(json.dumps({'received_hex': message.hex(), 'frames': seq}), flush=True)
    finally:
        if ack_task:
            ack_task.cancel()
            try: await ack_task
            except asyncio.CancelledError: pass
asyncio.run(main())
