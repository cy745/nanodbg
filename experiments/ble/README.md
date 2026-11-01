# BLE device probes

These experimental sources target the specific instrumented firmware used in
the research. The numeric firmware addresses and scatter/gather layout are not
portable to arbitrary nano firmware. Build them as NanoApps homebrew apps with
its SDK; this repository does not yet package a complete reproducible device
build or installation toolchain. The device probes are one-shot diagnostics,
not part of the resident debugger.

`bt_hci.c` sends synchronous HCI commands using a temporary receive hook and a
firmware-specific staging object. No concurrent HCI caller is safe: the firmware
staging area and hook are shared with the system stack. Controller completion
status, not the firmware send return value, determines command success.

`btscanprobe.c` scans briefly and stores the first matching payload from a
manufacturer advertisement with company field `ffff` and prefix `NDBG` in
`/Apps/Data/rawprobe.txt`. `btadvertiseprobe.c` reads 1-26 bytes from
`/Apps/Data/ble-tx.bin`, advertises for 15 seconds and stops. The host commands
are described in the top-level README. These are experimental test identifiers,
not a production Bluetooth protocol. Data is unauthenticated and broadcast in
cleartext. The files are persistent; remove sensitive payloads after testing.

`btechoprobe.c` performs two receive-then-transmit windows during a single
launch, then stops. After deploying it as `BTRawProbe`, start the Windows host
command as soon as the homebrew surface is visible:

```sh
python -m nanodbg wait-app --timeout 65
python -m nanodbg ble roundtrip 0123456789abcdef00 aabbcc00ff112280ff
```

The timing is tied to this probe: five seconds after launch it scans for ten
seconds, rebroadcasts the first matching payload for ten seconds, then repeats
once. Start the host command immediately after `wait-app`; another client can
win the first-payload race. This test has no authentication, sequence numbers,
acknowledgement, retry or delivery guarantee. The Windows host was tested with
the instrumented iPod; other hosts remain unverified. The RX hook points into
the running app, so do not switch away while either receive window is active.

`btsimprobe.c` tests concurrent nonconnectable advertising and passive
scanning for 12 seconds, then disables both. On the research device the
controller accepted all setup/cleanup commands (status 0); LE Read Supported
States returned `ff ff ff 1f 00 00 00 00`. In one run the device received
47 matching `NDBG` advertisements containing `00c001d0ffee` with no malformed
reports, and a concurrently running Windows scanner received 16 copies of the
device's `ND-SIM-2026` advertisement. This demonstrates both directions during
the same enabled interval, not reliable delivery or connection support. The
same RX hook lifetime restriction applies; run only on the matching firmware.
