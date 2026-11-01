import json
import tempfile
import unittest
from pathlib import Path

from nanodbg.deploy import prepare, stage, verify
from nanodbg.transport import TransportError


class DeployTests(unittest.TestCase):
    def test_backup_write_and_verify(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            root = base / 'target'
            (root / 'Executables').mkdir(parents=True)
            (root / 'Startup').mkdir()
            (root / 'AllApps.pack').write_bytes(b'old')
            entries = [(Path('Executables/Probe.hbapp'), b'app'),
                       (Path('AllApps.pack'), b'new'),
                       (Path('Startup/autolaunch'), b'Probe')]
            backup = stage(root, base / 'backups', entries)
            self.assertEqual((backup / 'AllApps.pack').read_bytes(), b'old')
            manifest = json.loads((backup / 'manifest.json').read_text())
            self.assertIsNone(manifest[0]['old_sha256'])
            verify(root, entries)
            (root / 'AllApps.pack').write_bytes(b'broken')
            with self.assertRaisesRegex(TransportError, 'Fresh mount verification failed'):
                verify(root, entries)

    def test_prepare_refuses_invalid_autostart(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(TransportError):
                prepare(tmp, '../escape')


if __name__ == '__main__':
    unittest.main()
