"""Keep derived configuration inside this process, outside Actions environment logs."""
import json
import os
import subprocess
import sys
import traceback

import run_probe as probe

try:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Disposable hosted probe only")
    config = json.loads(os.environ["REMOTE_PROBE_JSON"])
    os.environ["PROBE_CONFIG_JSON"] = json.dumps(config["probe"])
    os.environ["PROBE_CA_PATH"] = str(probe.ROOT / ".generated/root.crt")
    result = subprocess.run([sys.executable, str(probe.ROOT / "scripts/configure.py")], capture_output=True)
    if result.returncode:
        raise RuntimeError("Private configuration/discovery failed")
    probe.main()
except Exception:
    (probe.BUILD / "private-probe.log").write_text(traceback.format_exc())
    print("Remote reproduction failed; details retained only in encrypted evidence.", flush=True)
    raise SystemExit(1)
finally:
    if not (probe.BUILD / "diagnostics.enc").exists():
        probe.seal_evidence(None, None)
