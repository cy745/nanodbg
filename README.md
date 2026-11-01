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
| Build, deploy and autostart | Not implemented; write commands are disabled after filesystem corruption |
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
python -m nanodbg screenshot screen.bmp
python -m nanodbg tap 120 200
python -m nanodbg home
python -m nanodbg reboot
```

The last two commands currently work only on Windows. Device permissions and
drivers depend on the host. With suitable local Python packaging tools, the
project can also be installed with `pip install .`; the installed command is
`nanodbg`. The runtime has no third-party Python dependencies.

## Filesystem incident

On 2026-11-02, a Windows native deployment followed by reboot produced a damaged
FAT32 app index on the test device. The cause has not been established. The
device filesystem was repaired and its original app files restored from a local
backup; after eject and remount the app index matched the backup and Windows
filesystem checks reported no errors. `deploy` and `restore` are disabled until
the write/eject path has been investigated. There is no automated deployment
loop yet.
The observations and proposed validation are recorded in the
[filesystem investigation](docs/filesystem-investigation.md).

## Development

Run offline tests with `python -m unittest discover -s tests`. No tests write to
an attached device. The project does not contain Apple firmware, disk images,
device backups or memory dumps. Please do not commit those artifacts.

The original device-side project is [nano7-untethered](https://github.com/olievans123/nano7-untethered);
its license notices accompany the experimental patch.
