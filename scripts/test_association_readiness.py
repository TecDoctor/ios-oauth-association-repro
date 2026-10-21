"""Synthetic public fixtures for read-only OS association matching."""
import unittest
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
