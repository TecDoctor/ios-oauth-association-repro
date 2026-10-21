"""Source-free timing experiment; no app, account, endpoint or cloud credentials."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

if os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
    raise SystemExit('Only disposable hosted runners are allowed')
output = Path('results/maestro-version.json')
output.parent.mkdir(exist_ok=True)
report = {'version_timeout_seconds': 240, 'notification': os.environ['PROBE_NOTIFICATION']}
try:
    devices = json.loads(subprocess.check_output(['xcrun', 'simctl', 'list', 'devices', 'available', '--json'], text=True))
    candidates = [d for runtime, entries in devices['devices'].items() if runtime.endswith('iOS-27-0')
                  for d in entries if d.get('name') == 'iPhone 17']
    if not candidates:
        raise RuntimeError('Bundled iPhone 17 / iOS 27.0 is missing; no device or runtime will be created')
    device = candidates[0]
    if device['state'] != 'Booted':
        subprocess.run(['xcrun', 'simctl', 'boot', device['udid']], check=True, timeout=180)
    start = time.monotonic()
    subprocess.run(['xcrun', 'simctl', 'bootstatus', device['udid'], '-b'], check=True, timeout=600)
    report['bootstatus_seconds'] = round(time.monotonic() - start, 3)
    env = {k: v for k, v in os.environ.items() if k in {'DEVELOPER_DIR', 'HOME', 'JAVA_HOME', 'LANG', 'LC_ALL', 'PATH', 'TMPDIR'}}
    env.update(MAESTRO_CLI_NO_ANALYTICS='1', MAESTRO_CLI_NO_UPDATE_NOTIFICATION='1')
    if os.environ['PROBE_NOTIFICATION'] != 'default':
        env['MAESTRO_CLI_ANALYSIS_NOTIFICATION_DISABLED'] = 'true'
    if os.environ['PROBE_NOTIFICATION'] == 'no-update-check':
        env['MAESTRO_DISABLE_UPDATE_CHECK'] = 'true'
    binary = str(Path(os.environ['RUNNER_TEMP']) / 'maestro/maestro/bin/maestro')
    start = time.monotonic()
    child = subprocess.Popen([binary, '--version'], env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = child.communicate(timeout=240)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        stdout, stderr = child.communicate(timeout=15)
        report['timed_out'] = True
    report.update(elapsed_seconds=round(time.monotonic()-start, 3), exit_code=child.returncode,
                  stdout=stdout[-4000:], stderr=stderr[-4000:])
    lines = stdout.strip().splitlines()
    report['passed'] = child.returncode == 0 and bool(lines) and lines[-1].strip() == '2.10.0'
finally:
    output.write_text(json.dumps(report, indent=2)+'\n')
if not report.get('passed'):
    raise SystemExit(1)
