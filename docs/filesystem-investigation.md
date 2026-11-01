# Filesystem write investigation

## Observed

On the Windows test device, a native deployment followed by a panic reboot did
not start the probe. The app index was unreadable and Windows `chkdsk` reported
an invalid first allocation unit and a lost chain. After filesystem repair,
the app files were restored from a prior backup. A later eject/remount produced
an app index matching that backup, and a read-only `chkdsk` reported no problems.

The deployment used temporary files on the iPod volume, flushed each file,
replaced the destination, locked and dismounted the volume, and sent SCSI
eject. The earlier WSL workflow copied files in place, ran `sync`, unmounted the
partition and then ejected. These are multiple differences, so the observation
does not identify which operation or interaction caused the corruption. Panic
reboot, device-side filesystem state, competing host services, device caching,
host mount lifecycle and the FAT rename/replace path remain hypotheses.

The disabled native write implementation is intentionally excluded from the
public repository. `home` and `disk` do not implement an install transaction.
Do not treat a successful SCSI eject or a same-session file read as proof that
FAT metadata was durably persisted or that device and host caches are coherent.

## Next validation

1. Reproduce the write and replacement sequence against disposable FAT32 disk
   images and validate them after unmount, including injected failures. This can
   test host filesystem assumptions but cannot prove device-side cache safety.
2. Establish observable ownership transitions and durable flush behavior for
   both the host volume and the device. Record failure modes separately from
   successful commands, and rule out interfering clients.
3. Only after image-level checks, design an isolated hardware experiment with
   recoverable test data and compare hashes and filesystem consistency across
   fresh disconnect/reconnect and reboot cycles. Keep deployment disabled until
   the complete sequence is reproducible.
