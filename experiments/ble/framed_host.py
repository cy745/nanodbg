import asyncio, json, secrets, sys
from nanodbg.ble import advertise, COMPANY_ID

def frames(message, session):
    if not 1 <= len(message) <= 216 or len(session) != 2:
        raise ValueError('message must contain 1-216 bytes and session must be 2 bytes')
    parts = [message[i:i+18] for i in range(0, len(message), 18)]
    return [bytes([0xa1]) + session + bytes([i, len(parts)]) + p for i, p in enumerate(parts)]

async def main(message):
    from bleak import BleakScanner
    packets = frames(message, secrets.token_bytes(2))
    expected = None
    matched = asyncio.Event()
    responses = 0
    def callback(device, adv):
        nonlocal responses
        if expected is not None and adv.manufacturer_data.get(COMPANY_ID) == expected:
            responses += 1
            matched.set()
    async with BleakScanner(detection_callback=callback):
        for i, packet in enumerate(packets):
            expected = packet
            matched.clear()
            task = asyncio.create_task(advertise(packet, 15))
            try:
                await asyncio.wait_for(matched.wait(), 15)
                if i == 0:
                    # Deliberately ignore initial acknowledgements while continuing retransmission.
                    await asyncio.sleep(2)
                print(json.dumps({'frame': i, 'payload': packet.hex(), 'responses': responses}), flush=True)
            finally:
                task.cancel()
                try: await task
                except asyncio.CancelledError: pass
            await asyncio.sleep(.6)
    print(json.dumps({'message_hex': message.hex(), 'frames_confirmed': len(packets)}), flush=True)

if __name__ == '__main__':
    asyncio.run(main(bytes.fromhex(sys.argv[1])))
