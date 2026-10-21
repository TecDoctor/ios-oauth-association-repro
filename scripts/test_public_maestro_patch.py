"""Offline packaging checks for an opt-in public driver experiment."""
from pathlib import Path
import tempfile
import unittest
import zipfile

import patch_public_maestro as patcher


class PublicDriverPatchTest(unittest.TestCase):
    def test_patch_is_exact_and_never_silently_reapplied(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / patcher.RELATIVE_SOURCE
            source.parent.mkdir(parents=True)
            source.write_text(patcher.OLD)
            patcher.patch(root)
            self.assertEqual(source.read_text(), patcher.NEW)
            self.assertNotIn('.runningBackground', source.read_text())
            with self.assertRaises(ValueError):
                patcher.patch(root)

    def test_only_three_runner_resources_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jar = root / 'driver.jar'
            with zipfile.ZipFile(jar, 'w') as archive:
                archive.writestr('driver.class', b'unchanged-class')
                for name in patcher.RESOURCES:
                    archive.writestr(name, b'original-runner')
                    resource = root / 'maestro-ios-driver/src/main/resources' / name
                    resource.parent.mkdir(parents=True, exist_ok=True)
                    resource.write_bytes(b'experimental-runner')
            patcher.package(root, jar)
            with zipfile.ZipFile(jar) as archive:
                self.assertEqual(archive.read('driver.class'), b'unchanged-class')
                for name in patcher.RESOURCES:
                    self.assertEqual(archive.read(name), b'experimental-runner')
