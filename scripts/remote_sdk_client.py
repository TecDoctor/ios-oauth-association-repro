"""Disposable hosted-client transport using private owner Make targets, never cloud credentials."""
from contextlib import nullcontext
import ipaddress
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
from urllib.parse import urlparse

_DIAGNOSTICS = None


def root():
    if os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise RuntimeError('Disposable hosted runner required')
    path = Path(os.environ['RUNNER_TEMP']) / 'sdk-transport'
    path.mkdir(mode=0o700, exist_ok=True)
    return path


def record_failure(args, code, stdout, stderr):
    if _DIAGNOSTICS is None:
        return
    # Only connect() opts in; key generation must never enter evidence.
    # The private-evidence owner seals this directory before upload.
    def tail(value):
        if isinstance(value, bytes):
            value = value.decode(errors='replace')
        return (value or '')[-32768:]
    output = {'program': Path(args[0]).name, 'exit_code': code,
              'stdout_tail': tail(stdout), 'stderr_tail': tail(stderr)}
    (_DIAGNOSTICS / 'transport-failure.json').write_text(json.dumps(output))


def checked(args, *, data=None, timeout=120, output_path=None):
    try:
        # A verbose daemon must inherit a private file, never our capture pipe.
        with (output_path.open('w') if output_path else nullcontext()) as output:
            options = {'stdout': output, 'stderr': subprocess.STDOUT} if output else {'capture_output': True}
            result = subprocess.run(args, input=data, text=True, timeout=timeout, **options)
    except subprocess.TimeoutExpired as error:
        record_failure(args, 'timeout', error.stdout, error.stderr)
        raise RuntimeError('Client setup timed out; private command output withheld') from None
    if result.returncode:
        detail = result.stderr
        if output_path:
            with output_path.open('rb') as stream:
                stream.seek(max(0, output_path.stat().st_size - 32768))
                detail = stream.read()
        record_failure(args, result.returncode, result.stdout, detail)
        raise RuntimeError('Client setup failed; private command output withheld')
    return result.stdout


def validated(config):
    endpoint = str(ipaddress.IPv4Address(config['endpoint']))
    if not re.fullmatch(r'[A-Za-z0-9+/]{43}=', config['wireguard_public_key']):
        raise ValueError('Invalid transport public key')
    if not re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]+={0,2}', config['ssh_host_key']):
        raise ValueError('Invalid SSH host public key')
    domains = config['domains']
    if not isinstance(domains, list) or not domains or any(
        not isinstance(d, str) or not re.fullmatch(r'[a-z0-9]+(?:[.-][a-z0-9]+)*', d) for d in domains
    ):
        raise ValueError('Invalid disposable client domains')
    health = urlparse(config['health_url'])
    if health.scheme != 'https' or health.hostname not in domains or health.username or health.password or health.port:
        raise ValueError('Health URL must use a configured HTTPS domain')
    if 'ca_pem' in config and (not isinstance(config['ca_pem'], str)
            or not config['ca_pem'].startswith('-----BEGIN CERTIFICATE-----')):
        raise ValueError('Invalid public CA certificate')
    return endpoint, domains


def keys():
    path = root()
    config = json.loads(os.environ.pop('REMOTE_PROBE_JSON'))
    endpoint, domains = validated(config)
    private = checked(['wg', 'genkey']).strip()
    public = checked(['wg', 'pubkey'], data=private).strip()
    checked(['ssh-keygen', '-q', '-t', 'ed25519', '-N', '', '-f', str(path / 'ssh')])
    (path / 'public.json').write_text(json.dumps({'wireguard': public, 'ssh': (path / 'ssh.pub').read_text().strip()}))
    (path / 'known_hosts').write_text('10.77.0.1 ' + config['ssh_host_key'] + '\n')
    if 'ca_pem' in config:
        (path / 'root.crt').write_text(config['ca_pem'])
        checked(['openssl', 'x509', '-in', str(path / 'root.crt'), '-noout'])
    (path / 'client.json').write_text(json.dumps({'domains': domains, 'health_url': config['health_url']}))
    tunnel = path / 'probe.conf'
    tunnel.write_text('[Interface]\nPrivateKey = ' + private + '\nAddress = 10.77.0.6/32\nMTU = 1280\n'
                      '[Peer]\nPublicKey = ' + config['wireguard_public_key'] + '\nEndpoint = ' + endpoint +
                      ':51820\nAllowedIPs = 10.77.0.1/32\nPersistentKeepalive = 25\n')
    tunnel.chmod(0o600)
    (path / 'ssh_config').write_text('Host sdk-cluster\n  HostName 10.77.0.1\n  User e2e\n'
        f'  IdentityFile {path / "ssh"}\n  IdentitiesOnly yes\n  StrictHostKeyChecking yes\n'
        f'  UserKnownHostsFile {path / "known_hosts"}\n  ConnectTimeout 20\n  ServerAliveInterval 10\n  ServerAliveCountMax 2\n')
    print('Disposable public peer prepared; register slot 6 while the app builds.', flush=True)


def connect(*, diagnostics=None):
    global _DIAGNOSTICS
    _DIAGNOSTICS = diagnostics
    path = root()
    config = json.loads((path / 'client.json').read_text())
    checked(['sudo', '-n', 'env', 'LOG_LEVEL=verbose', shutil.which('wg-quick') or 'wg-quick',
             'up', str(path / 'probe.conf')], output_path=(_DIAGNOSTICS or path) / 'wireguard-startup.log')
    (path / 'tunnel-active').touch()
    ssh = ['ssh', '-F', str(path / 'ssh_config')]
    # The controller registers the published key during app compilation.
    # Fail once if the prepared cluster is unavailable; never create it here.
    checked(ssh + ['sdk-cluster', 'true'], timeout=30)
    if not (path / 'root.crt').exists():
        # The cluster's owner task already downloaded this public CA.
        # Retrieve it only through the pinned SSH host identity.
        certificate = checked(ssh + ['sdk-cluster', 'cat /home/e2e/cluster/root.crt'], timeout=30)
        (path / 'root.crt').write_text(certificate)
        checked(['openssl', 'x509', '-in', str(path / 'root.crt'), '-noout'])
    owner = ['make', '-s', '-C', 'private-owner']
    checked(owner + ['caddy.forward.setup'])
    (path / 'redirect-installed').touch()
    forward = ssh + ['-N', '-f', '-M', '-S', str(path / 'socket'), '-o', 'ExitOnForwardFailure=yes',
                     '-L', '127.0.0.1:8443:127.0.0.1:443']
    # ssh -f leaves its background child holding stdout/stderr. Give that child
    # an owned file, so communicate() on make can finish when the launcher exits.
    forward_log = (_DIAGNOSTICS or path) / 'ssh-forward.log'
    command = shlex.join(forward) + ' > ' + shlex.quote(str(forward_log)) + ' 2>&1'
    checked(owner + ['caddy.forward', 'CADDY_SSH_HOST=sdk-cluster', 'CADDY_FORWARD_COMMAND=' + command])
    checked(['sudo', 'tee', '-a', '/etc/hosts'], data='\n127.0.0.1 ' + ' '.join(config['domains']) + '\n')
    certificate = 'CADDY_CERTIFICATE_PATH=' + str(path / 'root.crt')
    checked(owner + ['-o', 'caddy.download', '-o', 'caddy.untrust.mac', 'caddy.trust.mac', certificate])
    checked(owner + ['-o', 'caddy.download', 'caddy.trust.iossim', certificate])
    checked(['curl', '--fail', '--silent', '--show-error', '--max-time', '120', config['health_url']], timeout=125)
    print('Existing owner forwarding and OS trust tasks passed; remote HTTPS is ready.', flush=True)


def cleanup():
    path = root()
    failures = []
    commands = []
    if (path / 'socket').exists():
        commands.append(['ssh', '-F', str(path / 'ssh_config'), '-S', str(path / 'socket'), '-O', 'exit', 'sdk-cluster'])
    if (path / 'redirect-installed').exists():
        commands.append(['make', '-s', '-C', 'private-owner', 'caddy.forward.remove'])
    if (path / 'tunnel-active').exists():
        commands.append(['sudo', '-n', shutil.which('wg-quick') or 'wg-quick', 'down', str(path / 'probe.conf')])
    for command in commands:
        try:
            checked(command)
        except (RuntimeError, OSError, subprocess.TimeoutExpired):
            failures.append('owned client cleanup failed')
    shutil.rmtree(path)
    if failures:
        raise RuntimeError('; '.join(failures))


if __name__ == '__main__':
    import sys
    try:
        if sys.argv[1:] == ['keys']:
            keys()
        elif sys.argv[1:] == ['cleanup']:
            cleanup()
        else:
            raise ValueError('Expected keys or cleanup')
    except Exception:
        # Configuration and subprocess exceptions may contain secret endpoint values.
        print('Remote client operation failed; private details withheld.', file=sys.stderr)
        raise SystemExit(1)
