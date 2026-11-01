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
    async def wait_notice(number, first=None, expected=None):
        async def recv_first():
            while True:
                data = await q.get()
                if len(data)>=5 and data[:3]==bytes([0xb0,number,0]):
                    return data
        packet = first or await asyncio.wait_for(recv_first(),15)
        if number == 0:
            deadline = asyncio.get_running_loop().time() + 3
            repeats = 0
            while True:
                remaining = deadline - asyncio.get_running_loop().time()
                if remaining <= 0: break
                try: other = await asyncio.wait_for(q.get(), remaining)
                except asyncio.TimeoutError: break
                if other == packet: repeats += 1
            if not repeats: raise ValueError('first frame did not repeat')
        else: repeats = None
        total=packet[3]
        if not 1 <= total <= 12: raise ValueError("bad fragment count")
        data=bytearray()
        for seq in range(total):
            if packet[:4] != bytes([0xb0,number,seq,total]): raise ValueError('bad notice frame')
            data.extend(packet[4:])
            ack=bytes([0xb1,number,seq])
            if seq + 1 < total:
                packet=await exchange(ack, lambda d, seq=seq: len(d)>=5 and d[:4]==bytes([0xb0,number,seq+1,total]))
            else:
                await exchange(ack, lambda d:d==bytes([0xb2,number,total]))
        if expected is None:
            if len(data)!=5 or data[4]!=0: raise ValueError('invalid startup payload')
        elif data != expected:
            raise ValueError('device outbox payload mismatch')
        print(json.dumps({'device_payload_hex': data.hex(), 'rounds_completed': number,
                          'bytes': len(data), 'frames': total,
                          'first_frame_repeats': repeats}), flush=True)
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
            if round_index == 1:
                while not q.empty(): q.get_nowait()
                await asyncio.sleep(4)
                observations = []
                while not q.empty(): observations.append(q.get_nowait())
                if b'\xa5'+session not in observations:
                    raise ValueError('completion was not observed during readiness delay')
                print(json.dumps({'completion_survived_delay_seconds': 4,
                                  'observations': observations.count(b'\xa5'+session)}), flush=True)
            first_notice=await exchange(b'\xb3'+session, lambda d: len(d)>=5 and d[:3]==bytes([0xb0,round_index,0]))
            await wait_notice(round_index, first_notice, request)
        await exchange(b'\xa6'+session, lambda d: d == b'\xa7'+session)
        print('shutdown acknowledged; waiting for cleanup', flush=True)
        await asyncio.sleep(4)
    print('done', flush=True)
if __name__ == '__main__':
    asyncio.run(main())
