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

`btstreamprobe.c` and `stream_host.py` exercise four sequential distinct
requests in one launch while scanning and advertising stay enabled. The host
uses the first byte as a test sequence and waits for an exact echoed payload
before the next request. On one Windows/iPod run all four echoed successfully;
the device logged four successful `LE Set Advertising Data` completions while
scanning was enabled, zero malformed reports, and successful scan and
advertising cleanup. Run `python -m experiments.ble.stream_host` from the
repository root immediately after `wait-app` with this probe deployed.

This is a bounded 42-second diagnostic, not a general transport: there is one
pending receive slot, no retry, session identifier, peer authentication,
fragmentation, or delivery guarantee. The receive hook is shared with the
firmware; the command helper chains its temporary hook through the probe hook.
Hook replacement and the pending slot have not been stress-tested for races or
coexistence with the system Bluetooth stack. The app must remain active through
cleanup. Cleartext manufacturer advertisements are visible to nearby devices.

Restoring the baseline app after this run again timed out during deploy's reboot
confirmation, although the deployed files had passed remount verification and
nanodbg could still query the device. A separate `nanodbg reboot` then observed
USB removal/return and `wait-app` confirmed the baseline surface. The intermittent
first-attempt failure remains unexplained; automatic recovery is not guaranteed.

`btframedprobe.c` and `framed_host.py` test a single stop-and-wait session
using a two-byte random session tag, one-byte sequence and fragment count, and
up to 18 message bytes per fragment. Deploy the probe, run `wait-app`, then
immediately run `python -m experiments.ble.framed_host HEXDATA` from the repo
root on Windows. One device run sent 96 bytes (`00` through `5f`) in six
fragments: all six echoes matched; the device reported six accepted fragments,
15 duplicates, no malformed frames, and a reassembled byte sequence verified
against the original. The first host acknowledgement was deliberately delayed
while its advertisement kept repeating. Controller update and cleanup statuses
were all zero.

This is still a bounded 65-second, one-message prototype, max 216 bytes. The
host repeats each advertisement until its echo or a 15-second timeout; a timeout
aborts rather than starting a new retry attempt. It does not prove delivery under
loss, device-to-host application messages, session recovery, or security. The
16-bit session tag is not authentication and can collide. Another advertiser can
claim the device session first, acknowledgements are forgeable, pending data is
one slot, and completed messages persist in the device log in cleartext. This
protocol and the hook remain experimental and firmware-specific.

`btoutboundprobe.c` and `outbound_host.py` exercise the reverse direction:
the device reads `/Apps/Data/nanodbg-outbound.bin` (1–216 bytes), initiates
fragmented advertising, and waits for a matching acknowledgement before the
next fragment. In one run a 103-byte file was received and reassembled exactly
by Windows in six fragments. The device logged six successful advertisement
updates, all acknowledgements, no malformed reports, and successful cleanup.
The temporary device file was removed after testing. Run the host with
`python -m experiments.ble.outbound_host` immediately after `wait-app`.

This is a separate 65-second, one-message experiment, not yet an integrated
bidirectional service. It uses a fixed session value, cleartext unauthenticated
broadcasts, one receive slot and no host-side persistence or recovery; the
controller and hook coexistence caveats above still apply. Nearby senders can
forge acknowledgements, and a disconnect or timeout aborts the experiment.

`btduplexprobe.c` and `duplex_host.py` combine both directions into a
40-second request/reply diagnostic. On Windows with the probe installed,
place the 40 bytes `ff` down through `d8` in
`/Apps/Data/nanodbg-outbound.bin`, then run
`python -m experiments.ble.duplex_host` immediately after `wait-app`. A device
run completed two distinct sessions in one launch: 31- and 47-byte host
requests were reassembled exactly, and both 40-byte device replies were
reassembled and compared by the host. The device recorded two completed
rounds, 16 duplicate packets, zero malformed reports, and successful scan and
advertising shutdown. Remove the temporary file afterwards.

This is a fixed request/reply test, not a continuous interactive debugger API.
It reads a static response at startup, runs for 40 seconds, uses unauthenticated
advertisements and a two-byte session identifier, and has a single pending RX
slot. It has no recovery after process exit, loss timeout, packet integrity
check, concurrency protection or guaranteed delivery. The RX hook must remain
installed only while the app remains alive. Mounting the iPod before the timer
finishes can displace the app and prevent clean hook and radio teardown; wait
for the complete interval before mounting, or reboot to recover. In one early
run premature mounting lost the final device log; the repeated run above waited
and captured teardown successfully. A separate deployment reboot confirmation
also timed out once and needed a standalone reboot.

`btserviceprobe.c` and `service_host.py` extend the duplex diagnostic with
user-specified hexadecimal requests and a host-initiated shutdown. After
installing the probe and supplying `/Apps/Data/nanodbg-outbound.bin`, run
`python -m experiments.ble.service_host HEXREQUEST [HEXREQUEST ...]` as soon
as `wait-app` reports the app. Each request receives the static file contents.
After the final exchange the host requests shutdown, observes a pre-cleanup
acknowledgement, and waits four seconds for the device to restore its hook and
turn off scanning and advertising. A 120-second fallback timer also stops the
probe. In a device run, two custom requests and a 24-byte binary response
matched; the device log confirmed the shutdown request, hook restoration and
successful HCI stop commands. The acknowledgement alone does not prove cleanup:
verify the log after the wait, especially if the connection is interrupted.

This remains a finite experiment, not a general interactive transport: the
response is a file loaded once at startup, a stalled session cannot be reset,
the protocol has no authentication or integrity and its short session tags can
collide. The cleanup marker records a pointer write, not proof that firmware
callbacks have quiesced. Do not switch apps or mount media before cleanup.

`btrecoveryprobe.c` and `recovery_host.py` add an experimental session reset.
The host diagnostic intentionally sends only the first fragment of a two-part
request, sends a new reset token, and then executes the hexadecimal requests
passed on the command line. On one iPod run, the device log recorded reset in
receive state after one accepted fragment, followed by two byte-exact new
requests, responses, and successful explicit cleanup. Duplicate reset tokens are ignored by the device. Use the same outbound file and launch instructions as
`service_host.py`; invoke `python -m experiments.ble.recovery_host HEX [HEX ...]`.

Reset is unauthenticated, discards the active message, and is not automatic on
host timeout. This test covers abandoning an incoming message, not host process crashes,
radio reconnection, or reliable exactly-once delivery. A reset token uses only two bytes and can
collide with an earlier token. The prior hook lifetime and cleanup limitations
also apply.


`btrecoverytxprobe.c` and `recovery_tx_host.py` test interruption in the
other direction. The host starts a response, receives its first fragment,
and deliberately sends no acknowledgement before issuing a reset. It then
sends a new multi-fragment request, repeats the previous reset for three
seconds after its first fragment, and completes two exchanges. The test
expects `/Apps/Data/nanodbg-outbound.bin` to contain 40 bytes descending
from `ff` to `d8`; the first request must span at least two fragments. Run
`python -m experiments.ble.recovery_tx_host HEX [HEX ...]` with the
corresponding diagnostic probe installed.

On one hardware run, the device logged reset in transmit state (`02`) after
one request fragment, counted 17 old reset advertisements while the next
request was in progress, and completed two requests with byte-exact
three-fragment responses. The log also recorded hook restoration and
successful scan and advertising stop commands. The counter is specific to
that experiment and is not a delivery guarantee. Only the most recent reset
token is remembered: an older token from before a subsequent reset can still
interrupt a session. The security, collision, cleanup and concurrency limits
above still apply.
