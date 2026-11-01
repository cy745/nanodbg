import asyncio, json, secrets
from nanodbg.ble import advertise, COMPANY_ID
from experiments.ble.framed_host import frames

async def main():
    from bleak import BleakScanner
    q = asyncio.Queue()
    def callback(device, adv):
        data = adv.manufacturer_data.get(COMPANY_ID, b'')
        if data: q.put_nowait(data)
    async def exchange(tx, accept):
        task = asyncio.create_task(advertise(tx, 15))
        try:
            async def recv():
                while True:
                    data = await q.get()
                    if accept(data): return data
            return await asyncio.wait_for(recv(), 15)
        finally:
            task.cancel()
            try: await task
            except asyncio.CancelledError: pass
    requests = [bytes(range(31)), bytes(range(80,127))]
    expected = bytes((255-i)%256 for i in range(40))
    sessions = [secrets.token_bytes(2), secrets.token_bytes(2)]
    while sessions[1] == sessions[0]: sessions[1] = secrets.token_bytes(2)
    async with BleakScanner(detection_callback=callback):
        for request, session in zip(requests, sessions):
            for p in frames(request, session):
                await exchange(p, lambda d, p=p: d == p)
            first = await exchange(b'\xa4'+session, lambda d: len(d)>=6 and d[:4] == b'\xa2'+session+b'\x00')
            reply = bytearray(); packet = first; index = 0; total = packet[4]
            if not 1 <= total <= 12: raise ValueError('invalid reply count')
            while True:
                if packet[:4] != b'\xa2'+session+bytes([index]) or packet[4] != total: raise ValueError('bad frame')
                reply.extend(packet[5:]); ack=b'\xa3'+session+bytes([index]); index += 1
                if index == total:
                    await exchange(ack, lambda d: d == b'\xa5'+session)
                    break
                packet = await exchange(ack, lambda d, i=index: len(d)>=6 and d[:4] == b'\xa2'+session+bytes([i]))
            if reply != expected: raise ValueError('reply differs from device file')
            print(json.dumps({'session':session.hex(), 'request_hex':request.hex(), 'reply_hex':reply.hex(), 'reply_frames':total}), flush=True)
    print('two rounds verified', flush=True)
if __name__ == '__main__':
    asyncio.run(main())
