import asyncio, json, secrets, sys
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
    requests = [bytes.fromhex(x) for x in sys.argv[1:]]
    if not requests: raise ValueError('provide one or more hexadecimal requests')
    sessions = []
    for request in requests:
        frames(request, b'\0\0')
        session = secrets.token_bytes(2)
        while session in sessions: session = secrets.token_bytes(2)
        sessions.append(session)
    async with BleakScanner(detection_callback=callback):
        abandoned_session = secrets.token_bytes(2)
        partial = frames(b'tx-abandon', abandoned_session)[0]
        await exchange(partial, lambda d: d == partial)
        first = await exchange(b'\xa4'+abandoned_session, lambda d: len(d)>=6 and d[:4] == b'\xa2'+abandoned_session+b'\x00')
        if first[4] <= 1: raise ValueError('response must span multiple frames')
        print('first response fragment received; simulating interruption without ACK', flush=True)
        reset = b'\xa8' + secrets.token_bytes(2)
        await exchange(reset, lambda d: d == b'\xa9' + reset[1:])
        print('reset acknowledged', flush=True)
        for round_index, (request, session) in enumerate(zip(requests, sessions)):
            for frame_index, p in enumerate(frames(request, session)):
                await exchange(p, lambda d, p=p: d == p)
                if round_index == 0 and frame_index == 0:
                    await advertise(reset, 3)
                    print('resent old reset during new request', flush=True)
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
            if reply != bytes((255-i)%256 for i in range(40)): raise ValueError('reply mismatch')
            print(json.dumps({'session':session.hex(), 'request_hex':request.hex(), 'reply_hex':reply.hex(), 'reply_frames':total}), flush=True)
        await exchange(b'\xa6'+session, lambda d: d == b'\xa7'+session)
        print('shutdown acknowledged; waiting for cleanup', flush=True)
        await asyncio.sleep(4)
    print('done', flush=True)
if __name__ == '__main__':
    asyncio.run(main())
