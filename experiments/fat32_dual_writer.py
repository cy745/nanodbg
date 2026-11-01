"""Demonstrate stale independent FAT writers on a disposable image only.

Requires ``pip install .[fatlab]``. Does not open or modify any device.
This models independent filesystem caches, not Windows or iPod behavior.
"""
import tempfile
from pathlib import Path

from pyfatfs.PyFat import PyFat
from pyfatfs.PyFatFS import PyFatFS


def run_case(shared):
    # Image path is always created here; callers cannot supply a device path.
    with tempfile.TemporaryDirectory(prefix='nanodbg-fatlab-') as directory:
        image = Path(directory) / 'disposable.img'
        image.touch()
        filesystem = PyFat()
        filesystem.mkfs(str(image), fat_type=32, size=64 * 1024 * 1024)
        filesystem.close()
        initial = PyFatFS(str(image))
        try:
            initial.makedirs('/Apps/Startup', recreate=True)
        finally:
            initial.close()

        first = PyFatFS(str(image))
        second = PyFatFS(str(image)) if shared else None
        try:
            first.writebytes('/Apps/AllApps.pack', b'N' * 65000)
        finally:
            first.close()
        if second is None:
            second = PyFatFS(str(image))
        try:
            second.writebytes('/Apps/Startup/diag.txt', b'X' * 65000)
        finally:
            second.close()
        check = PyFatFS(str(image), read_only=True)
        try:
            return (check.readbytes('/Apps/AllApps.pack') == b'N' * 65000,
                    check.readbytes('/Apps/Startup/diag.txt') == b'X' * 65000)
        finally:
            check.close()


def main():
    serial = run_case(False)
    overlapping = run_case(True)
    print(f'Serial writers: index={serial[0]}, diagnostic={serial[1]}')
    print(f'Stale overlapping writers: index={overlapping[0]}, diagnostic={overlapping[1]}')
    if serial != (True, True):
        raise SystemExit('Control scenario failed')
    if overlapping == (True, True):
        raise SystemExit('The expected stale-cache effect was not reproduced')
    print('Model demonstrates corruption; it does not prove the iPod incident cause.')


if __name__ == '__main__':
    main()
