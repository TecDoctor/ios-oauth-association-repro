"""Synthetic public fixtures for read-only OS association matching."""
import unittest
import tempfile
from pathlib import Path
from unittest import mock
import subprocess
import probe_sdk_handoff as probe
from probe_sdk_handoff import associations_approved


class AssociationReadinessTest(unittest.TestCase):
    def snapshot(self, domain='auth.example.test', identity='TEAM.example.app', approval='approved'):
        return f'Service: webcredentials\nApp ID: {identity}\nDomain: {domain}\nSite/Fmwk Approval: {approval}\n'

    def test_developer_retrieval_mode_keeps_the_same_domain_identity(self):
        for domain in ('auth.example.test', 'auth.example.test?mode=developer'):
            self.assertTrue(associations_approved(self.snapshot(domain), 'TEAM.example.app', ['auth.example.test']))

    def test_other_hosts_identities_pending_and_unknown_queries_fail(self):
        for snapshot in (
            self.snapshot('other.example.test?mode=developer'),
            self.snapshot('auth.example.test?mode=developer', identity='OTHER.example.app'),
            self.snapshot('auth.example.test?mode=developer', approval='unspecified'),
            self.snapshot('auth.example.test?mode=developer&extra=true'),
            self.snapshot('auth.example.test?mode=unexpected'),
        ):
            self.assertFalse(associations_approved(snapshot, 'TEAM.example.app', ['auth.example.test']))

    def test_slow_observation_does_not_start_authentication_or_reset_deadline(self):
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(probe, 'EVIDENCE', Path(temporary)), \
             mock.patch.object(probe, 'record_host_load'), \
             mock.patch.object(probe.time, 'sleep'), \
             mock.patch.object(probe.time, 'monotonic', side_effect=[0, 1, 1, 121, 121, 126, 126, 130]), \
             mock.patch.object(probe, 'run', side_effect=[
                 subprocess.TimeoutExpired(['swcutil', 'show'], 120), self.snapshot().encode(),
             ]) as run:
            self.assertEqual(probe.wait_for_associations('device', '/swcutil', 'TEAM.example.app', ['auth.example.test']), 130)
            self.assertEqual(run.call_count, 2)
            for call in run.call_args_list:
                self.assertEqual(call.args[0][-1], 'show')
                self.assertEqual(call.kwargs['timeout'], 120)

    def test_pending_registration_fails_at_original_deadline(self):
        with tempfile.TemporaryDirectory() as temporary, \
             mock.patch.object(probe, 'EVIDENCE', Path(temporary)), \
             mock.patch.object(probe, 'record_host_load'), \
             mock.patch.object(probe.time, 'sleep'), \
             mock.patch.object(probe.time, 'monotonic', side_effect=[0, 1, 1, 9, 9, 10]), \
             mock.patch.object(probe, 'run', return_value=b'') as run:
            with self.assertRaisesRegex(RuntimeError, 'before authentication'):
                probe.wait_for_associations('device', '/swcutil', 'TEAM.example.app', ['auth.example.test'], timeout=10)
            run.assert_called_once()
            self.assertEqual(run.call_args.kwargs['timeout'], 9)

    def test_status_observation_preserves_one_confirmation(self):
        marker = "- tapOn:\n    text: 'Continue|続ける'\n    optional: true\n    retryTapIfNoChange: false\n"
        modified = probe.observe_status_before_confirmation(marker)
        self.assertEqual(modified.count('- tapOn:'), 1)
        self.assertLess(modified.index('scrollUntilVisible'), modified.index('- tapOn:'))
        self.assertIn('timeout: 120000', modified)
        self.assertNotIn('repeat:', modified)
        with self.assertRaises(ValueError):
            probe.observe_status_before_confirmation(marker + marker)
