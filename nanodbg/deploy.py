"""Experimental host-side deployment primitives; device coordination is separate."""
import hashlib
import json
import os
import re
import time
from pathlib import Path

from .transport import TransportError


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(source, autostart):
    source = Path(source).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,23}', autostart or ''):
        raise TransportError('Autostart must be a simple 1-23 character app name')
    result = []
    for folder, suffix in (('Executables', '.hbapp'), ('Icons', '.bin')):
        directory = source / folder
        if not directory.is_dir() or directory.is_symlink():
            raise TransportError(f'Missing or symlinked {folder} directory')
        for p in sorted(directory.iterdir()):
            if p.is_symlink():
                raise TransportError('Symlinks are not accepted in deploy source')
            if p.is_file() and p.suffix.lower() == suffix:
                result.append((Path(folder) / p.name, p.read_bytes()))
    if not any(rel == Path('Executables') / (autostart + '.hbapp') for rel, _ in result):
        raise TransportError('Autostart executable is absent from source')
    pack = source / 'AllApps.pack'
    if not pack.is_file() or pack.is_symlink():
        raise TransportError('Missing or symlinked AllApps.pack')
    data = pack.read_bytes()
    # The registration pack stores the bundle name as UTF-16LE.
    if autostart.encode('utf-16le') not in data and autostart.encode('ascii') not in data:
        raise TransportError('Autostart name not found in app pack')
    result += [(Path('AllApps.pack'), data),
               (Path('Startup/autolaunch'), autostart.encode('ascii'))]
    return result


def stage(root, backup_root, entries):
    """Back up all targets before in-place writes. Failure leaves backup intact."""
    root = Path(root)
    backup = Path(backup_root) / (time.strftime('%Y%m%d-%H%M%S') + '-' + os.urandom(4).hex())
    backup.mkdir(parents=True)
    manifest = []
    for rel, data in entries:
        dst = root / rel
        if dst.is_symlink() or not dst.parent.is_dir() or dst.parent.is_symlink():
            raise TransportError(f'Unsafe or absent target directory: {rel}')
        old = dst.read_bytes() if dst.exists() else None
        if old is not None:
            saved = backup / rel
            saved.parent.mkdir(parents=True, exist_ok=True)
            with saved.open('xb') as f:
                f.write(old); f.flush(); os.fsync(f.fileno())
            if saved.read_bytes() != old:
                raise TransportError(f'Backup verification failed: {rel}')
        manifest.append({'path': rel.as_posix(), 'old_sha256': digest(old) if old is not None else None,
                         'new_sha256': digest(data)})
    with (backup / 'manifest.json').open('x', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2); f.flush(); os.fsync(f.fileno())
    print(f'Backup ready: {backup}', flush=True)
    for rel, data in entries:
        dst = root / rel
        if dst.is_file() and dst.read_bytes() == data:
            continue
        with dst.open('wb') as f:
            f.write(data); f.flush(); os.fsync(f.fileno())
        if dst.read_bytes() != data:
            raise TransportError(f'Immediate verification failed: {rel}; backup at {backup}')
    return backup


def verify(root, entries):
    for rel, data in entries:
        if (Path(root) / rel).read_bytes() != data:
            raise TransportError(f'Fresh mount verification failed: {rel}')
