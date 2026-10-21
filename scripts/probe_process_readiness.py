"""Standalone public process/pipe timing probe; no application source or services."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

with tempfile.TemporaryDirectory() as temporary:
    marker = Path(temporary) / 'ready'
    child = (
        'import os,signal,time; from pathlib import Path; time.sleep(1.5); '
        'signal.signal(signal.SIGTERM,signal.SIG_IGN); '
        f'Path({str(marker)!r}).write_text(str(os.getpid())); '
        'print(os.getpid(),flush=True); time.sleep(120)'
    )
    launcher = f'import subprocess,sys; subprocess.Popen([sys.executable,"-c",{child!r}])'
    began = time.monotonic()
    process = subprocess.Popen([sys.executable, '-c', launcher], stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        deadline = began + 60
        while not marker.exists() or process.poll() is None:
            if time.monotonic() >= deadline:
                raise RuntimeError('Child readiness exceeded 60 seconds')
            time.sleep(.02)
        ready = time.monotonic()
        try:
            process.communicate(timeout=1)
            raise AssertionError('Inherited pipe unexpectedly closed')
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.communicate(timeout=.1)
            raise AssertionError('TERM-resistant child unexpectedly exited')
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
        stdout, _ = process.communicate(timeout=5)
        assert int(stdout.strip()) == int(marker.read_text())
        assert process.poll() is not None
        result = dict(passed=True, startup_seconds=round(ready-began,3),
                      timeout_and_cleanup_seconds=round(time.monotonic()-ready,3))
        Path('results').mkdir(exist_ok=True)
        Path('results/process-readiness.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result))
    finally:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate(timeout=5)
