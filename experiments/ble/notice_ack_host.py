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
    async def wait_notice(number):
        async def recv():
            while True:
                data = await q.get()
                if len(data) == 6 and data[:2] == bytes([0xb0, number]):
                    return data
        data = await asyncio.wait_for(recv(), 15)
        if number == 0:
            # Delay ACK while observing the same device-generated message again.
            deadline = asyncio.get_running_loop().time() + 3
            repeats = 0
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0: break
                try: other = await asyncio.wait_for(q.get(), remaining)
                except asyncio.TimeoutError: break
                if other == data: repeats += 1
            if not repeats: raise ValueError('notice did not repeat while ACK was delayed')
        else:
            repeats = None
        confirm = await exchange(b'\xb1'+data[1:], lambda d: d == b'\xb2'+data[1:])
        print(json.dumps({'device_notice_hex': data.hex(), 'rounds_completed': number,
                          'device_tick': int.from_bytes(data[2:], 'little'),
                          'observations_during_delay': repeats, 'confirm_hex': confirm.hex()}), flush=True)
    requests = [bytes.fromhex(x) for x in sys.argv[1:]]
    if not requests: raise ValueError('provide one or more hexadecimal requests')
    sessions = []
    for request in requests:
        frames(request, b'\0\0')
        session = secrets.token_bytes(2)
        while session in sessions: session = secrets.token_bytes(2)
        sessions.append(session)
    async with BleakScanner(detection_callback=callback):
        await wait_notice(0)
        for round_index, (request, session) in enumerate(zip(requests, sessions), 1):
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
            if reply != request[::-1]: raise ValueError('dynamic reply mismatch')
            print(json.dumps({'session':session.hex(), 'request_hex':request.hex(), 'reply_hex':reply.hex(), 'reply_frames':total}), flush=True)
            await wait_notice(round_index)
        await exchange(b'\xa6'+session, lambda d: d == b'\xa7'+session)
        print('shutdown acknowledged; waiting for cleanup', flush=True)
        await asyncio.sleep(4)
    print('done', flush=True)
if __name__ == '__main__':
    asyncio.run(main())
