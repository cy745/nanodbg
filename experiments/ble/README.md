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


`btdynamicprobe.c` and `dynamic_host.py` exercise a device-generated
response without an outbound file. After receiving each complete request,
the iPod reverses its bytes in memory and transmits that result; the host
verifies the result before starting the next request. Run
`python -m experiments.ble.dynamic_host HEX [HEX ...]` with the dynamic probe
installed. Messages are still restricted to 1–216 bytes, and this is a
bounded diagnostic rather than an interactive application API.

One hardware run sent a 37-byte and a 7-byte request; the device recorded
both, and the host received the byte-reversed replies in three and one
fragments respectively. It requested shutdown, and the device recorded hook
restoration and successful scan and advertising stop statuses. This proves
those two device-side computations, not arbitrary application-originated
messages or an indefinitely running transport. The Windows host currently
uses WinRT advertising; the other recovery, security and cleanup caveats
continue to apply.


`btnoticeprobe.c` and `notice_host.py` add device-originated notices to the
dynamic response diagnostic. At startup the device advertises `b0`, the
completed-round count and a little-endian 32-bit LVGL tick. Two seconds
after completing each exchange it publishes another notice if still idle.
The host listens for each notice and checks its round count before continuing.
Run `python -m experiments.ble.notice_host HEX [HEX ...]` with the notice
probe installed; start the host soon after `wait-app` reports the app.

In one hardware run the host received the first notice before starting any
BLE advertisement, then received notices after each of two completed
requests. The device log matched all three notice payloads and recorded
hook restoration and successful scan and advertisement stop statuses.
The startup notice is unsolicited; the later notices follow completion of
exchanges. They have no acknowledgement, buffering, identity verification or
delivery guarantee and share one advertisement slot with responses. Timing
can overwrite a response acknowledgement if a host is delayed. Tick values
are local device counters, not wall-clock times. This does not yet provide a
reliable, general device-originated message channel. The other limitations
of the recovery and dynamic probes still apply.


`btnoticeackprobe.c` and `notice_ack_host.py` add a bounded acknowledgement
experiment. The device keeps advertising the same `b0` notice and ignores
other incoming commands until it receives `b1` with the same five-byte
notice identifier. It then advertises `b2` with that identifier and accepts
the next request. Run `python -m experiments.ble.notice_ack_host HEX [HEX ...]`
with the corresponding probe installed. The host deliberately delays the
first acknowledgement for three seconds.

In one device run, the host observed five additional copies during that
delay, then observed confirmation and completed two requests. Three notice
confirmations appeared on both host and device; the device also recorded
shutdown, hook restoration, and successful scan and advertising stop statuses.
The fixed-size device log was truncated after the notice acknowledgement count,
so its trailing summary fields were unavailable for that run.

This is still a one-slot diagnostic, not a reliable general queue: the
notice can replace a response-completion advertisement after two seconds,
there is no authentication or durable state, and an absent host blocks other
commands until the 120-second watchdog. Notice identity can collide after
counter wrap or reboot. Observation of repeated advertisements and one
acknowledgement does not prove recovery from lost confirmations, process
restarts, or arbitrary radio loss. Existing hook and platform limitations
remain.


`btnoticereadyprobe.c` and `notice_ready_host.py` address the completion/notice
collision in the previous experiment. Once a request completes, the device
continues advertising `a5` until the host sends `b3` plus that session ID.
Only then does it publish the next notice, which uses the same `b1`/`b2`
acknowledgement as above. Startup notices remain unsolicited; subsequent
notices are delivered only after a host readiness signal. Run
`python -m experiments.ble.notice_ready_host HEX [HEX ...]` with this probe.

On one device run the host deliberately delayed readiness four seconds after
the first response and observed seven completion advertisements during the
delay; the subsequent notice and a second exchange also completed. The
device recorded two readiness signals, three notice acknowledgements, two
completed exchanges, hook restoration, and successful stop statuses. This
probe uses a larger log buffer, and the full summary was captured.

This only addresses that particular advertisement-slot race. There is no
durable queue, identity verification, or general process-restart recovery;
an unacknowledged notice still blocks commands until the watchdog. Readiness
is unauthenticated and short session identifiers can collide. BLE advertising
and the hook are experimental, and a delayed device shutdown acknowledgement
alone does not prove teardown.


`btdeviceframesprobe.c` and `device_frames_host.py` extend the readiness
experiment with a 40-byte device-generated payload split into three BLE
advertisements. Each fragment carries the round and sequence number; the host
acknowledges it before the device publishes the next. The payload contains
the device tick, round and deterministic test bytes. Start the installed
probe and invoke `python -m experiments.ble.device_frames_host HEX [HEX ...]`.

In one hardware run, the host reconstructed and checked three distinct
40-byte device messages (nine fragments total) alongside two bidirectional
request/response exchanges. The first message started before any host BLE
request; the host delayed its first ACK for three seconds and observed six
additional copies. The host also observed the first request completion for
four seconds before granting readiness. Device logs recorded all nine
fragments, three message acknowledgements, both completed requests, hook
restoration and successful scan/advertising stop statuses.

The 40-byte content and three-fragment count are diagnostic constants, not
a general application API. The protocol has a single outstanding message,
uses one-byte round and sequence fields without authentication, and does
not persist data or recover automatically across host/device restart. The
first-fragment repeat test does not establish recovery from loss of later
ACKs, radio disconnects, or a missing final confirmation. Other hook and
platform limitations described above still apply.


`nano_ble_outbox.h` and `nano_ble_outbox.c` extract the experimental
device-originated fragmentation into a small C interface. Initialize it with
a transport publish callback, then call `nano_ble_outbox_send` with an ID
and 1–216 bytes; pass matching ACK packets to `nano_ble_outbox_ack`. It copies
the payload and allows one pending message. The caller must serialize access,
provide an available advertising transport, and handle scheduling, readiness,
shutdown, and transport failures. `btoutboxprobe.c` demonstrates integration;
`outbox_host.py` runs the corresponding host diagnostic.

In one successful hardware run the application sent device-generated 5-, 40-,
and 100-byte payloads (1, 3, and 6 fragments), and the host reassembled and
checked them along with two request/response exchanges. The device recorded
all three acknowledgements, hook restoration, and successful HCI stop
statuses. The first run failed after receipt of the 5-byte message because
the host test still checked 40 bytes; it was fixed and the device rebooted
before the successful run. `test_outbox.c` additionally exercises 1, 19, 20
and 216-byte boundaries, invalid input, busy state, mismatched ACKs, copying,
and simulated publish failures on a host compiler.

Only 5, 40 and 100 bytes were exercised on hardware. This API remains an
experimental building block, not a standalone reliable transport: the
publish callback controls the shared advertising slot, the demo callback
checks command return values but does not treat nonzero controller status as
failure, ACKs and short IDs are unauthenticated, and the caller must maintain
object lifetime until completion. It has no queue, timeout policy, durable
recovery, concurrency protection, or automatic hook lifecycle management.


`btruntimeoutboxprobe.c` and `runtime_outbox_host.py` exercise the outbox
with runtime application data: after each complete inbound request and
reverse-byte diagnostic reply, the device application passes the original
request buffer and length to the outbox. Run
`python -m experiments.ble.runtime_outbox_host HEX [HEX ...]` with this probe.
Its startup message is still device-generated; subsequent outbox messages
are copies of host-originated requests, not independent device-originated
application messages. The watchdog for this experiment is 180 seconds.

A hardware run used a single zero byte and 216 randomly generated bytes.
The host verified both the reversed diagnostic responses and the exact
original data returned through the outbox. The 216-byte response and outbox
message each occupied 12 fragments. Device logs recorded a 216-byte outbox
message, three outbox acknowledgements, two completed requests, hook
restoration, and successful scan/advertising stop statuses. This probe treats
a nonzero HCI controller status as a command failure as well as checking the
transport return value. No nonzero controller status was induced in this run.
The other one-slot, authentication, persistence, watchdog, and hook caveats
remain.


### Interactive host client

`python -m nanodbg ble interactive` runs the same runtime-outbox protocol in
a single process, accepting hex messages on stdin and emitting JSON events.
It validates responses and the outbox data, uses unique session IDs within a
process, and refuses to reuse a session after a protocol failure. It does not
authenticate peers or guarantee recovery after a timeout. Run it promptly after
the probe starts because the device watchdog runs even while waiting for input.

On 2026-11-02 the interactive command was tested on the device with a one-byte
request and a 20-byte, multi-fragment request in one process. Both reverse
responses and both outbox messages matched. The probe log reported two
completed rounds, `hook restored`, and zero transport/controller status for
scan and advertisement shutdown. The host shutdown event alone is not proof
of those cleanup operations.


### Device-initiated successive outbox messages

`btautonomousprobe.c` and `python -m experiments.ble.autonomous_host` test
two device-generated notices without sending any application request or
readiness command. After the startup notice is acknowledged, the app schedules
a 40-byte notice; after that notice is acknowledged, it schedules a 100-byte
notice. The first four bytes contain the app's current tick, the fifth contains
the sequence number, and the rest is a reproducible device-generated pattern.
The host acknowledges each fragment and then sends a separate `b4` shutdown
request. A two-second delay after each completed notice preserves the completion
advertisement before publishing the next message.

On 2026-11-02, a Windows host received and checked all three notices from the
iPod: startup (5 bytes), followed by independent 40- and 100-byte notices.
The app reported ticks 7291 and 11760 for the latter, zero completed inbound
request rounds, three acknowledged notices, restored hook, and zero transport
and controller statuses for stopping scan and advertisement. This verifies
the specific experiment, not an unrestricted duplex service: the two messages
are acknowledgement-gated and fixed in advance, there is one advertising slot,
no authentication or confidentiality, and the host cannot concurrently send
application data while a notice is pending. The 180-second watchdog and hook
lifecycle limitations still apply. The experiment adds a separate `b4`/`b5`
shutdown command only after both notices, not a general cancellation protocol.


The integrated host command `python -m nanodbg ble interactive --probe
autonomous` receives these two notices and then accepts normal hexadecimal
requests in the same session. On 2026-11-02 it was tested on hardware receiving
both notices followed by a 21-byte request; the reversed response and original
outbox echo matched, and the device reported hook restoration and successful
scan/advertising shutdown. The `--probe` selection must match the deployed
firmware. Notifications are received before interactive input; they are not
an asynchronous background subscription or unrestricted duplex transport.


### Runtime touch-driven device data

`bttapprobe.c` replaces the autonomous timer notices with two screen buttons.
Each accepted LVGL click constructs a six-byte notice in the app: little-endian
32-bit device tick, button ID (1 or 2), and one-based accepted-click count.
Message IDs start at `0x80`. The probe accepts a click only when its outbox is
free and no host request is in progress; busy clicks are dropped. It also
retains the runtime echo request protocol. `python -m experiments.ble.tap_host`
uses nanodbg touch injection to click the two buttons, receives each notice,
and sends one host request between the clicks. The script requires the matching
probe, the resident touch debugger and Windows BLE advertising.

A hardware test on 2026-11-02 received button/count pairs (1,1) and (2,2) at
device ticks 6319 and 12553 respectively. Between them a seven-byte host
request returned the correct reverse response and original outbox echo. Device
logs confirm both button callbacks, one completed request, restored hook and
successful scan/advertising shutdown. This verifies runtime-originated event
data across both directions, not general asynchronous full-duplex operation:
there is still no event queue or concurrency arbitration, and messages are
unauthenticated broadcasts. Never treat the two-byte session or one-byte
notice IDs as security.


### Bounded event queue experiment

The queued interactive client now recognizes an unsolicited first fragment
while waiting for a request or shutdown response. It acknowledges the entire
notice and retries the interrupted command, retaining the notice for the
caller. IDs 0x80–0xfe are reserved for events and request rounds are limited
to 127 to avoid collision with the request echo IDs. While waiting for terminal
input, it receives notices and completes their acknowledgments before acting on
any simultaneous input. The probe still has a finite watchdog and a
bounded, nonpersistent queue.

On 2026-11-02 `python -m experiments.ble.queue_contention_host` injected two
touches before starting a 40-byte request. The host received event IDs 0x80
and 0x81 during the request and verified both the reverse reply and original
echo. The device log recorded both notices acknowledged before the request,
zero dropped events, an empty queue, restored hook and controller shutdown.
This demonstrates arbitration for this specific probe, not a general BLE
connection or protection against spoofing or packet loss.

On 2026-11-02 `python -m experiments.ble.queue_idle_host` started the queued
CLI in a separate process, left its stdin idle, and injected two touches. Both
notifications were printed and acknowledged before any input was sent. The
same CLI then completed a 40-byte request, verified the reverse reply and echo,
and acknowledged shutdown. The device log is the separate evidence of hook and
controller cleanup. This is serialized notice handling, not simultaneous radio
transmissions or an authenticated, persistent stream.

#### Variable-length device-originated data

Build `btqueueprobe.c` with `QUEUE_VARIABLE_DATA=1` (alongside `bt_hci.c`,
`nano_ble_outbox.c`, `nano_ble_queue.c`, `nano_ble_messages.c` and
`nano_ble_inbox.c`) to make buttons A and B enqueue
40 and 216 bytes respectively. The first four bytes are the device tick in
little-endian order, followed by the button and event counter. The rest is
generated on the device from the tick, byte offset and button. Without the
define, the original six-byte touch messages are unchanged.

On 2026-11-02 `python -m experiments.ble.queue_variable_host` injected both
button presses and independently checked every byte, then completed a 40-byte
host request and clean shutdown. The 216-byte notice used 12 outbox fragments
and included both `00` and `ff`; the device log recorded four completed
notices including startup and echo, no dropped touches, an empty queue, hook
restoration and successful scan and advertising disable commands. This
verifies the queue's maximum message size on this device, but the generated
data is still a diagnostic payload rather than a general application API.

#### Reusable device-side message submission

`nano_ble_messages.[ch]` packages ID assignment and the bounded FIFO for an
application to submit its own bytes. After initializing the messages object
and outbox, call `nano_ble_messages_submit(&messages, bytes, length, &id)`
from the serialized application context. The data is copied, so the caller
may reuse its buffer. `NANO_MSG_OK` means accepted into the queue, not delivered;
invalid input, a full queue and exhaustion of the 127 IDs have distinct return
codes. The caller must schedule `nano_ble_messages_pump` when the outbox is
available, route received acknowledgments through `nano_ble_outbox_ack`, and
notify its application of completion if needed. A failed initial publish
retains the front message for a later pump. Do not reinitialize while the host
session is running: reusing an ID can cause its duplicate filter to drop data.

On 2026-11-02 the queue probe was rebuilt to use this interface and tested on
the iPod with `queue_variable_host`: 40- and 216-byte device-generated
messages and a 40-byte host request matched byte for byte. Native C tests also
cover copy semantics, capacity, retry, busy outbox and ID exhaustion. This is
an application-facing queue helper, not a complete standalone Bluetooth stack:
the application still owns radio setup, the receive hook, arbitration, timers,
ACK handling and cleanup. It remains an unauthenticated experimental protocol.

#### Reusable device-side request reassembly

`nano_ble_inbox.[ch]` provides a single-session buffer for inbound `a1`
fragments. The application calls `nano_ble_inbox_begin` with the session tag
and fragment count, then feeds frames to `nano_ble_inbox_accept` from its
serialized receive context. On `NANO_INBOX_COMPLETE`, `data` and `length`
contain the assembled message until the next begin or reset. A publish
callback sends the fragment acknowledgement; on failure, the inbox leaves its
state unchanged so the caller can retry. Earlier fragments are reported as
duplicates and out-of-order fragments are ignored. The caller still owns
session selection, arbitration, acknowledgements for duplicates, radio setup,
timeouts and cleanup.

On 2026-11-02, `python -m experiments.ble.inbox_host` sent a 216-byte binary
request to the rebuilt queue probe. The host verified both the device's
reversed diagnostic response and its original-data echo. The device log recorded
one completed 216-byte request, an acknowledged outbox, restored hook, and zero
transport and controller statuses for scan and advertising shutdown. Native C
tests cover all 12 fragments, duplicates, ordering and synthetic publish
failure. This is one hardware run, using Windows for the BLE host; it does not
establish loss recovery, cross-platform operation or delivery guarantees. The
16-bit session tags and cleartext advertisements provide no authentication.

`nano_ble_queue.[ch]` adds a four-entry FIFO of copied messages, each at most
216 bytes, and `test_queue.c` checks bounds, full and empty behavior, copying,
ordering and ring wrap. The caller must serialize queue access.
`btqueueprobe.c` uses it for touch events: one message may be advertising while
four others wait. A full queue rejects new clicks and counts the rejection.
The probe schedules the next notice two seconds after the previous notice is
confirmed, and gives queued notices priority over new host requests.
`python -m experiments.ble.queue_host` tests the matching firmware.

On 2026-11-02, the host injected six alternating button clicks before sending
any notice ACK. It then received the first five in FIFO order, sent a seven-byte
request and checked its reply and echo. The device log showed queue depths
one through four, one full-queue rejection, zero remaining entries, hook
restoration and successful scan/advertising shutdown. One deployment reboot
could not confirm USB removal; a subsequent explicit reboot was confirmed
before the test.

This remains an experiment: a full queue drops new events, overflow is only
recorded in the device log, messages are not persisted, only initial queued-message publish failures are
retried, and a two-second completion window plus single advertising
slot limits throughput. Host and device traffic still do not run concurrently;
there is no authentication or confidentiality. These observations do not
establish general reliable transport or cross-platform host support.


### Events during a host request and initial-publish retry

The queue probe now keeps its front message when the first attempt to publish
fails and schedules another attempt after two seconds, repeating until success
or the probe watchdog. This covers only the initial queued-notice publish, not
every fragment, lost completion, or recovery after restart. Persistent failures
can keep the queue blocked until the watchdog. The compile-time
`QUEUE_TEST_FAIL_ONCE` option injects one artificial failure for notice `0x80`
before making the HCI call; ordinary builds do not enable it.

The initial startup notice is also retried after two seconds if its first
publish fails. The retry continues until success or the 180-second watchdog;
the shared timer keeps queued messages from being published ahead of startup.
The separate `QUEUE_TEST_STARTUP_FAIL_ONCE` build option injects one failure
before the startup HCI call. In a 2026-11-02 hardware run, the device logged
that injection, scheduled a retry, published and received acknowledgement of
startup, and completed a 20-byte request with correct reverse and echo data.
The log also recorded hook restoration and zero scan/advertising stop statuses.
This simulated failure does not demonstrate recovery from a real controller
failure, a lost startup acknowledgement, or a continuously failing radio.

On 2026-11-02, `python -m experiments.ble.queue_race_host` ran with this
fault-injection build. After the first fragment of a 40-byte host request was
acknowledged, two taps were injected while the request remained in progress.
The request's reversed response and original echo matched. The device log
showed both events queued during the request, the deliberately injected
publish failure, retry scheduling, subsequent sends of IDs `0x80` and `0x81`,
and no dropped or remaining events. The host received both in order; cleanup
restored the hook and returned successful scan/advertising stop statuses.
This is a synthetic failure at the publish boundary, not a demonstrated HCI
controller error. It tests overlapping event creation and inbound traffic,
while radio transmissions are still serialized. The first deploy's reboot
was not confirmed; an explicit subsequent reboot succeeded before the run.
