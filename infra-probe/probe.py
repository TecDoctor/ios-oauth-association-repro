"""Synthetic hosted-only Docker/Caddy/Safari checks; no application dependencies."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def run(*args, timeout=180, **kwargs):
    return subprocess.run(args, timeout=timeout, check=True, **kwargs)


def output(*args):
    return run(*args, capture_output=True, text=True).stdout


def network():
    vm = json.loads(output('colima', 'ssh', '--', 'ip', '-j', '-4', 'route', 'get', '1.1.1.1'))[0]['prefsrc']
    vm = str(ipaddress.IPv4Address(vm))
    interfaces = json.loads(output('colima', 'ssh', '--', 'ip', '-j', '-4', 'addr'))
    assert any(a.get('local') == vm for i in interfaces for a in i.get('addr_info', []))
    mac = str(ipaddress.IPv4Address(output('colima', 'ssh', '--', 'getent', 'ahostsv4', 'host.lima.internal').split()[0]))
    with Path(os.environ['GITHUB_ENV']).open('a') as f:
        f.write(f'PROBE_VM_ADDRESS={vm}\nPROBE_MAC_ADDRESS={mac}\n')
        f.write(f'CADDY_CERTIFICATE_PATH={Path(os.environ["RUNNER_TEMP"]) / "caddy-root.crt"}\n')
    ssh = Path.home() / '.ssh'
    ssh.mkdir(exist_ok=True)
    with (ssh / 'config').open('a') as f:
        f.write('\nInclude ~/.colima/ssh_config\n')
    print(f'Docker VM bind address: {vm}; Mac upstream address: {mac}', flush=True)


def simulator():
    root = Path(os.environ['RUNNER_TEMP'])
    devices = json.loads(output('xcrun', 'simctl', 'list', 'devices', 'available', '-j'))['devices']
    candidates = [d for runtime, entries in devices.items() if runtime.endswith('iOS-26-2')
                  for d in entries if d['name'].startswith('iPhone')]
    if not candidates:
        raise RuntimeError('No existing iOS 26.2 iPhone; no additional devices will be created')
    candidates.sort(key=lambda d: ('SE' not in d['name'], d['name']))
    device = candidates[0]
    udid = device['udid']
    (root / 'probe-simulator').write_text(udid)
    print('Using existing hosted simulator:', device['name'], udid, flush=True)
    if device['state'] != 'Booted':
        run('xcrun', 'simctl', 'boot', udid)
    run('xcrun', 'simctl', 'bootstatus', udid, '-b', timeout=600)
    # This is the same simulator keychain operation used by the private CI.
    run('make', '-C', 'infra-probe', 'caddy.trust.iossim', f'SIMULATOR_UDID={udid}',
        f'CADDY_CERTIFICATE_PATH={root / "caddy-root.crt"}', timeout=180)
    nonce = os.environ['GITHUB_RUN_ID']
    deadline = time.monotonic() + 1000
    observed = False
    while time.monotonic() < deadline:
        try:
            run('xcrun', 'simctl', 'openurl', udid, f'https://localhost/?probe={nonce}')
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
            print('Safari startup:', type(error).__name__, flush=True)
        time.sleep(15)
        try:
            run('xcrun', 'simctl', 'io', udid, 'screenshot', str(root / 'safari-https.png'))
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
            print('Screenshot:', type(error).__name__, flush=True)
        logs = output('docker', 'compose', '-f', 'infra-probe/compose.yml', 'logs', '--no-color', 'caddy')
        for line in logs.splitlines():
            if '{' not in line:
                continue
            try:
                event = json.loads(line[line.index('{'):])
            except ValueError:
                continue
            request = event.get('request', {})
            if (request.get('uri') == f'/browser-proof?probe={nonce}'
                    and event.get('status') == 200
                    and 'iPhone' in json.dumps(request.get('headers', {}))):
                observed = True
        if observed:
            time.sleep(5)
            run('xcrun', 'simctl', 'io', udid, 'screenshot', str(root / 'safari-https.png'))
            break
    if not observed:
        raise RuntimeError('Safari did not complete trusted HTTPS and both upstream checks')
    (root / 'probe-result.json').write_text(json.dumps({
        'safari_trusted_https': True, 'container_route': True, 'mac_host_route': True,
        'certificate_sha256': hashlib.sha256((root / 'caddy-root.crt').read_bytes()).hexdigest(),
        'simulator': device['name'], 'udid': udid,
    }, indent=2))


if __name__ == '__main__':
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise RuntimeError('Only disposable GitHub-hosted runners are supported')
    {'network': network, 'simulator': simulator}[sys.argv[1]]()
