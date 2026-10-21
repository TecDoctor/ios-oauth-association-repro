"""Offline checks; never activate a tunnel or change the host."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import remote_sdk_client as client


class RemoteClientTest(unittest.TestCase):
    def config(self):
        return {'endpoint': '192.0.2.1', 'wireguard_public_key': 'A' * 43 + '=',
                'ssh_host_key': 'ssh-ed25519 ' + 'A' * 64,
                'domains': ['api.example.test', 'auth.example.test'],
                'health_url': 'https://api.example.test/health',
                'ca_pem': '-----BEGIN CERTIFICATE-----\nsynthetic\n-----END CERTIFICATE-----\n'}

    def test_rejects_invalid_transport_and_host_configuration(self):
        self.assertEqual(client.validated(self.config())[0], '192.0.2.1')
        for key, value in [('endpoint', 'invalid'), ('wireguard_public_key', 'bad'),
                           ('ssh_host_key', 'ssh-ed25519 bad\ninjection'),
                           ('domains', ['api.example.test\nmalicious']),
                           ('health_url', 'http://api.example.test/health'),
                           ('health_url', 'https://other.example.test/health'),
                           ('health_url', 'https://user:pass@api.example.test/health')]:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                config = copy.deepcopy(self.config());config[key] = value
                client.validated(config)

    def test_local_machine_is_rejected(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(RuntimeError):
            client.root()

    def test_connection_uses_owner_tasks_without_container_or_cloud_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'client.json').write_text(json.dumps(self.config()))
            with mock.patch.object(client, 'root', return_value=path), \
                 mock.patch.object(client, 'checked', return_value='') as checked, \
                 mock.patch.object(client.shutil, 'which', return_value='/bin/wg-quick'):
                client.connect()
            commands = [call.args[0] for call in checked.call_args_list]
            self.assertTrue(all(command[0] not in {'docker', 'gcloud', 'xcodebuild'} for command in commands))
            for target in ('caddy.forward.setup', 'caddy.forward', 'caddy.trust.mac', 'caddy.trust.iossim'):
                self.assertEqual(sum(target in c for c in commands), 1)
            self.assertEqual(sum(c[-1] == 'true' for c in commands), 1)
            self.assertTrue((path / 'tunnel-active').exists())
            self.assertTrue((path / 'redirect-installed').exists())

    def test_cleanup_continues_after_one_failure_and_removes_private_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'transport';path.mkdir()
            for name in ('socket', 'redirect-installed', 'tunnel-active', 'ssh'):
                (path / name).touch()
            with mock.patch.object(client, 'root', return_value=path), \
                 mock.patch.object(client, 'checked', side_effect=[RuntimeError('failure'), '', '']) as checked, \
                 self.assertRaises(RuntimeError):
                client.cleanup()
            self.assertEqual(checked.call_count, 3)
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
