"""Check a disposable hosted simulator alongside a synthetic Docker service."""
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request

assert os.environ.get('GITHUB_ACTIONS') == 'true'
assert os.environ.get('RUNNER_ENVIRONMENT') == 'github-hosted'
def run(*args, **kwargs):
    return subprocess.run(args, check=True, timeout=kwargs.pop('timeout', 30), **kwargs)

devices = json.loads(run('xcrun', 'simctl', 'list', 'devices', 'available', '-j', capture_output=True, text=True).stdout)['devices']
candidates = [d for runtime, entries in devices.items() if runtime.endswith('iOS-26-2') for d in entries if d['name'].startswith('iPhone')]
if not candidates:
    raise RuntimeError('No existing iOS 26.2 iPhone; refusing to create additional devices')
candidates.sort(key=lambda d: ('SE' not in d['name'], d['name']))
device = candidates[0]
udid = device['udid']
print('Selected existing simulator:', device['name'], udid, flush=True)
Path(os.environ['RUNNER_TEMP'], 'probe-simulator').write_text(udid)
if device['state'] != 'Booted':
    run('xcrun', 'simctl', 'boot', udid)
run('xcrun', 'simctl', 'bootstatus', udid, '-b', timeout=600)
# A host check proves the container survived boot; Safari provides visual evidence
# of simulator routing separately, without claiming that opening a URL proves it.
with urllib.request.urlopen('http://127.0.0.1:8080/', timeout=30) as response:
    assert b'Welcome to nginx' in response.read()
print('Docker HTTP check passed after simulator boot.', flush=True)
deadline = time.monotonic() + 600
attempt = 0
observed = False
while time.monotonic() < deadline:
    attempt += 1
    try:
        run('xcrun', 'simctl', 'openurl', udid, 'http://127.0.0.1:8080/', timeout=120)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print('Safari readiness attempt', attempt, type(error).__name__, flush=True)
    time.sleep(15)
    try:
        run('xcrun', 'simctl', 'io', udid, 'screenshot', str(Path(os.environ['RUNNER_TEMP'], 'simulator-proof.png')), timeout=90)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        print('Screenshot attempt', attempt, type(error).__name__, flush=True)
    logs = run('docker', 'compose', '-f', 'connectivity/compose.yml', 'logs', '--no-color', capture_output=True, text=True, timeout=60).stdout
    if any('GET / HTTP/' in line and ' 200 ' in line and 'iPhone' in line for line in logs.splitlines()):
        observed = True
        print('Container recorded a successful iPhone browser HTTP request.', flush=True)
        break
if not observed:
    raise RuntimeError('No successful iPhone browser request within the Safari readiness window')
