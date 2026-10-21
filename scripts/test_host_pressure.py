"""Read-only host load evidence contains no process or account data."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import probe_sdk_handoff as probe

class HostPressureTest(unittest.TestCase):
    def test_only_numeric_host_metrics_are_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with mock.patch.object(probe, 'EVIDENCE', root), \
                 mock.patch.object(probe.os, 'getloadavg', return_value=(3.0, 2.0, 1.0)), \
                 mock.patch.object(probe.os, 'cpu_count', return_value=4), \
                 mock.patch.object(probe.time, 'time', return_value=123.0):
                probe.record_host_load()
            self.assertEqual(json.loads((root / 'host-load.jsonl').read_text()),
                             {'time': 123.0, 'cpu_count': 4, 'load_average': [3.0, 2.0, 1.0]})
