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
try:
    run('xcrun', 'simctl', 'openurl', udid, 'http://127.0.0.1:8080/', timeout=300)
    time.sleep(30)
finally:
    run('xcrun', 'simctl', 'io', udid, 'screenshot', str(Path(os.environ['RUNNER_TEMP'], 'simulator-proof.png')), timeout=120)
print('Docker remained reachable from macOS after simulator boot. Inspect Safari screenshot separately.', flush=True)
