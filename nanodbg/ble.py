"""Host-side BLE experiment helpers. The device probe is separately deployed."""
import asyncio
import json
import sys

COMPANY_ID = 0xffff
PREFIX = b'NDBG'


def parse_payload(value, limit):
    try:
        data = bytes.fromhex(value)
    except ValueError as exc:
        raise ValueError('payload must be hexadecimal bytes') from exc
    if not data or len(data) > limit:
        raise ValueError(f'payload must contain 1-{limit} bytes')
    return data


async def scan(expected, duration):
    try:
        from bleak import BleakScanner
    except ImportError as exc:
        raise ValueError('BLE scan requires the optional bleak dependency') from exc
    seen = 0
    def callback(_device, advertisement):
        nonlocal seen
        data = advertisement.manufacturer_data.get(COMPANY_ID)
        if data == expected:
            seen += 1
            if seen == 1:
                print(json.dumps({'payload_hex': data.hex(), 'matched': True}), flush=True)
    async with BleakScanner(detection_callback=callback):
        print('BLE scan started', file=sys.stderr, flush=True)
        await asyncio.sleep(duration)
    if not seen:
        raise ValueError('no matching BLE advertisement observed')
    print(json.dumps({'matches': seen}), flush=True)


async def advertise(data, duration):
    if sys.platform != 'win32':
        raise ValueError('BLE advertising is currently implemented on Windows only')
    try:
        from winrt.windows.devices.bluetooth.advertisement import (
            BluetoothLEAdvertisementPublisher, BluetoothLEManufacturerData,
            BluetoothLEAdvertisementPublisherStatus,
        )
        from winrt.windows.storage.streams import DataWriter
    except ImportError as exc:
        raise ValueError('BLE advertising requires the optional Windows WinRT dependencies') from exc
    publisher = BluetoothLEAdvertisementPublisher()
    section = BluetoothLEManufacturerData()
    section.company_id = COMPANY_ID
    writer = DataWriter()
    writer.write_bytes(PREFIX + data)
    section.data = writer.detach_buffer()
    publisher.advertisement.manufacturer_data.append(section)
    publisher.start()
    try:
        for _ in range(50):
            status = publisher.status
            if status == BluetoothLEAdvertisementPublisherStatus.STARTED:
                break
            if status == BluetoothLEAdvertisementPublisherStatus.ABORTED:
                raise ValueError('Windows BLE advertising aborted; check Bluetooth radio and permissions')
            await asyncio.sleep(.1)
        else:
            raise ValueError('Windows BLE advertising did not start')
        print('BLE advertising started', file=sys.stderr, flush=True)
        await asyncio.sleep(duration)
    finally:
        publisher.stop()



async def roundtrip(payloads):
    """Run the bounded, two-window echo probe; start when its surface appears."""
    for index, data in enumerate(payloads, 1):
        print(json.dumps({'round': index, 'send_hex': data.hex()}), flush=True)
        await advertise(data, 8)
        await scan(data, 18)
    print(json.dumps({'rounds_completed': len(payloads)}), flush=True)


def run_roundtrip(values):
    if not 1 <= len(values) <= 2:
        raise ValueError('the two-window echo probe accepts one or two payloads')
    payloads = [parse_payload(value, 23) for value in values]
    if len(set(payloads)) != len(payloads):
        raise ValueError('use distinct payloads to distinguish the two rounds')
    asyncio.run(roundtrip(payloads))

def run(command, payload_hex, duration):
    if duration <= 0:
        raise ValueError('duration must be positive')
    data = parse_payload(payload_hex, 23 if command == 'advertise' else 26)
    asyncio.run(advertise(data, duration) if command == 'advertise' else scan(data, duration))
