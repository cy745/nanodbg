# nanodbg

An experimental native debugger for an iPod nano 7G with a specifically
instrumented firmware and resident. The goal is a cross-platform development
loop without iTunes or WSL; this is still research software, not a complete
setup or a general-purpose iPod debugger. Stock firmware is not supported.

## Status

| Feature | Status |
| --- | --- |
| Windows device discovery, status, screenshot, home, reboot | Tested on one instrumented device |
| Windows touch injection | Tested on the resident homebrew surface only |
| Linux SG_IO transport | Implemented; this package has not been validated on a native Linux host |
| Linux home, disk mode and reboot | Not implemented |
| macOS | Not implemented |
| Windows deploy and autostart | Experimental; tested end-to-end on one instrumented device |
| BLE advertisement experiment | Short binary payloads tested both ways on one Windows host and one device; not a connection or reliable stream |
| Build and automated restore | Not implemented |
| Native system foreground app, system-wide touch and buttons | Not implemented |

Reboot uses a firmware-specific panic path, not a graceful shutdown. The tool
checks the experimental handler fingerprint, waits for USB removal and return,
then ejects the storage. The status block identifies the resident homebrew
surface; it is not a general system foreground-app query. Only use the debugger
with the matching experimental firmware and avoid concurrent clients. The
device-side snapshot in [firmware](firmware/README.md) is not yet a complete
reproducible firmware build or installation guide.

## Usage

Python 3.9 or newer is required. From this repository's root, with the
instrumented device already attached:

```sh
python -m nanodbg devices
python -m nanodbg status
python -m nanodbg boot-status
python -m nanodbg screenshot screen.bmp
python -m nanodbg tap 120 200
python -m nanodbg home
python -m nanodbg reboot
python -m nanodbg deploy /path/to/Apps --autostart BTRawProbe --backup-dir /path/to/local-backups --reboot
python -m nanodbg wait-app --timeout 75
```

`boot-status` reads the resident boot record: registration completion indicates
that its registration step ran, and launch fields describe recorded launches
since boot, not necessarily the current foreground application.

`home`, `disk`, `reboot`, and `deploy` currently work only on Windows.
Deploy takes an already built Apps tree; it does not build firmware or apps.
It backs up overwritten files on another volume, writes in place, ejects,
remounts and checks bytes, then optionally reboots. Restore is manual. A pack
containing the application name is not proof that its registration is valid;
check `boot-status`, `wait-app`, and a screenshot after reboot. Device permissions and
drivers depend on the host. With suitable local Python packaging tools, the
project can also be installed with `pip install .`; the installed command is
`nanodbg`. The runtime has no third-party Python dependencies.

## Filesystem incident

On 2026-11-02, a Windows native deployment followed by reboot produced a damaged
FAT32 app index on the test device. The cause has not been established. The
device filesystem was repaired and its original app files restored from a local
backup; after eject and remount the app index matched the backup and Windows
filesystem checks reported no errors. The earlier corruption remains unexplained. An experimental in-place Windows
deployment path has subsequently passed fresh-mount and reboot checks on one
device. This limited result does not prove the sequence safe in all cases;
keep backups. Automated restore remains disabled.
The observations and proposed validation are recorded in the
[filesystem investigation](docs/filesystem-investigation.md).

## Development

Run offline tests with `python -m unittest discover -s tests`. No tests write to
an attached device. The project does not contain Apple firmware, disk images,
device backups or memory dumps. Please do not commit those artifacts.

The original device-side project is [nano7-untethered](https://github.com/olievans123/nano7-untethered);
its license notices accompany the experimental patch.

## Experimental BLE probes

On the tested firmware, one-shot device probes sent and received short binary
BLE advertisements. The device-side research sources are in
[experiments/ble](experiments/ble/README.md); they require the separately built
NanoApps SDK and are not part of the installed firmware by default. The
prototype changes shared controller settings and is not a reliable or secure
transport. Do not run concurrent Bluetooth activity during a test.

Install optional dependencies with `pip install .[ble]`. With the matching
probe deployed on the iPod and the host radio already on:

```sh
python -m nanodbg ble advertise 00ff8066aa1122330042 --duration 60
python -m nanodbg ble scan 00ff4e616e6f4442478001fe32303236 --duration 60
python -m nanodbg ble roundtrip 0123456789abcdef00 aabbcc00ff112280ff
```

Run each command with its corresponding device probe. The two-message
roundtrip has timing constraints described in the device probe README. Advertising is implemented and tested on Windows only.
Scanning uses Bleak and has been tested on Windows; Linux and macOS are
unverified. The commands do not enable or disable the host radio. Advertising
payloads are limited to 23 bytes and scanning matches up to 26 bytes. The
experimental `0xffff` manufacturer field is a test marker, not an assigned
company identifier for production use. These simple commands do not provide pairing, acknowledgement, encryption,
fragmentation or retransmission. The separately deployed runtime-outbox probe
has an experimental acknowledged fragment protocol, described below.


With the experimental `btruntimeoutboxprobe.c` firmware deployed and started,
`python -m nanodbg ble interactive` accepts one 1–216-byte hexadecimal message
per line. It emits JSON events for the device startup notice and each exchange;
enter `quit` or EOF after a successful request to request probe shutdown.
For example:

```text
00
00112233445566778899aabbccddeeff00112233
quit
```

The probe reverses each request for a diagnostic response and then sends the
original bytes via its device outbox. Apart from the startup notice, these are
not independent device-originated application messages. This protocol uses
unauthenticated, unencrypted broadcast, has short identifiers, and is not a
reliable stream. Host advertising currently requires Windows; other systems
have not been validated. The probe watchdog is 180 seconds, including idle
time. If the session fails or exits before its first completed request, clean
shutdown is not confirmed; the watchdog or reboot is needed. A shutdown event
confirms the device acknowledged the command and the host waited four seconds;
only the device log confirms hook and controller cleanup. See the probe README
for deployment and protocol limitations.

With the separately built autonomous outbox probe instead, use
`python -m nanodbg ble interactive --probe autonomous`. The client receives
the probe's two scheduled device-generated notices and prints `device_notice`
JSON events before accepting requests. It can then send requests and validate
their responses in the same process. Quitting without a request uses that
probe's dedicated shutdown command. This mode is specific to the experimental
probe and is sequential; it does not implement arbitrary simultaneous traffic.
