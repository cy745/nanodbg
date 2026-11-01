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
