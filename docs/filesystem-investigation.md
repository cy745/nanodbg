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

The earlier native write implementation is excluded from the public repository. `home` and `disk` do not implement an install transaction.
Do not treat a successful SCSI eject or a same-session file read as proof that
FAT metadata was durably persisted or that device and host caches are coherent.

## Further observations (2026-11-02)

The local resident source calls `hb_fs_write` for `Apps/Startup/diag.txt` during
its first home action, and can also write a previous trace during initialization.
The paths for both the diagnostic and autolaunch files were found in the live
resident's memory. This supports investigating device-side filesystem activity
around boot and USB enumeration, but does not establish when a write reached
disk, whether it overlapped the host, or the cause of the incident.

Windows documents that a successful
[`FSCTL_LOCK_VOLUME`](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ni-winioctl-fsctl_lock_volume)
flushes host cached data and confirms no open host files. It does not establish
that the iPod firmware has relinquished its own filesystem state. Windows also
documents that a dismounted volume can be mounted again when accessed, even by
[`GetLogicalDrives`](https://learn.microsoft.com/en-us/windows/win32/api/winioctl/ni-winioctl-fsctl_dismount_volume).
Earlier Windows reboot monitoring repeatedly called discovery, which uses that
API. The revised monitor uses USB PnP IDs while waiting; discovery is still
used before reboot, and the original volume is opened after USB returns. The
timing and actual effect on this device remain to be measured.

An isolated FAT32 model is reproducible with
`python experiments/fat32_dual_writer.py` after installing `.[fatlab]` in a
development environment. Two independent `pyfatfs` instances open the same
disposable image before either writes. Serial access preserved both synthetic
files; in the overlapping case both writes returned successfully but the first
file contained the second file's bytes on reopening. This is a demonstration
of the hazard of independent stale FAT caches, not a reproduction of Windows
`os.replace`, iPod firmware, or the observed hardware corruption. No device was
accessed during this test. `pyfatfs` 1.1.0 also failed in a separate sequential
overwrite experiment, so it is not an oracle for Windows FAT behavior.

## Next validation

1. Reproduce the original Windows write and replacement sequence against a
   disposable FAT32 image mounted by Windows, then validate it after unmount,
   including injected failures. A Windows native mounted-volume test may need
   elevated privileges; the Python-only model is not a substitute.
2. Establish observable ownership transitions and durable flush behavior for
   both the host volume and the device. Record failure modes separately from
   successful commands, and rule out interfering clients.
3. Extend hardware validation to more devices and interrupted writes; compare
   fresh-mount hashes and consistency before treating the experimental path as
   reliable. Automated restore remains disabled.

## Native Windows deployment experiment (2026-11-02)

A full Apps directory snapshot was saved and checked against the device before
writing. A new 65,792-byte scratch file survived eject and remount unchanged.
The replacement deployer then backed up targets, wrote files in place with
per-file flush and immediate verification, ejected and remounted, and verified
the installed data. An initial automatic remount failed with Windows error 21:
a handle held across eject prevented opening a new volume handle. Closing the
old handle before reopening fixed this in subsequent tests. This explains that
remount failure, not the earlier FAT corruption.

The full deploy/remount/reboot sequence subsequently completed on one iPod.
After reboot the installed bytes matched again, the resident reported four
registered apps and one launch, the BTRawProbe entry and timer files were
present, and a debugger screenshot displayed its diagnostic screen. Windows
read-only `chkdsk` reported no problems, but could not obtain exclusive access;
it is not a definitive consistency check. The root cause of the original
corruption, device-side ownership transitions and behavior under interruption
remain unresolved. No native Windows mounted-image test was performed. The
new deployer is experimental and has not been validated on other hosts.
