"""Run only on a disposable GitHub runner; never print raw subprocess output."""
import json
import shutil
import os
import plistlib
import struct
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / ".build"
BUILD.mkdir(exist_ok=True)


def run(args, timeout=1800, env=None):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, timeout=timeout, env=env)
    if result.returncode:
        # Arguments and output may include secret endpoints or identity.
        raise RuntimeError("Diagnostic subprocess failed; raw output withheld.")
    return result.stdout


def embedded_entitlements(binary):
    data = binary.read_bytes()
    if struct.unpack_from("<I", data)[0] != 0xFEEDFACF:
        raise RuntimeError("Unexpected executable architecture.")
    count = struct.unpack_from("<I", data, 16)[0]
    offset = 32
    for _ in range(count):
        command, size = struct.unpack_from("<II", data, offset)
        if command == 0x19:
            sections = struct.unpack_from("<I", data, offset + 64)[0]
            for index in range(sections):
                section = offset + 72 + index * 80
                name = data[section:section + 16].rstrip(b"\0")
                if name == b"__entitlements":
                    length = struct.unpack_from("<Q", data, section + 40)[0]
                    start = struct.unpack_from("<I", data, section + 48)[0]
                    return plistlib.loads(data[start:start + length].rstrip(b"\0"))
        offset += size
    return None


def seal_evidence(udid):
    evidence = BUILD / "private-evidence"
    evidence.mkdir(exist_ok=True)
    try:
        run(["xcrun", "simctl", "io", udid, "screenshot", str(evidence / "screen.png")], timeout=120)
    except Exception:
        pass
    try:
        logs = run(["xcrun", "simctl", "spawn", udid, "log", "show", "--last", "20m", "--style", "ndjson",
                    "--predicate", 'process == "swcd" OR subsystem CONTAINS "AuthenticationServices"'], timeout=120)
        (evidence / "association-service.log").write_bytes(logs)
    except Exception:
        pass
    archive = shutil.make_archive(str(BUILD / "private-diagnostics"), "zip", evidence)
    try:
        run(["openssl", "cms", "-encrypt", "-binary", "-aes256", "-in", archive,
             "-outform", "DER", "-out", str(BUILD / "diagnostics.enc"),
             str(ROOT / "diagnostics/recipient.pem")], timeout=120)
        print("Encrypted diagnostic evidence prepared.", flush=True)
    finally:
        Path(archive).unlink(missing_ok=True)
        shutil.rmtree(evidence)


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise SystemExit("This runner must only be used in disposable GitHub Actions VMs.")
    print("phase: project-generation", flush=True)
    run(["xcodegen", "generate", "--spec", ".generated-project.json"])
    print("phase: build", flush=True)
    run(["xcodebuild", "-project", "AssociationProbe.xcodeproj", "-scheme", "AssociationProbe",
         "-configuration", "Debug", "-sdk", "iphonesimulator", "-destination", "generic/platform=iOS Simulator",
         "-derivedDataPath", str(BUILD), "ARCHS=arm64", "ONLY_ACTIVE_ARCH=YES", "-jobs", "2", "build"])
    app = BUILD / "Build/Products/Debug-iphonesimulator/AssociationProbe.app"
    expected = plistlib.loads((ROOT / ".generated/App.entitlements").read_bytes())
    actual = embedded_entitlements(app / "AssociationProbe")
    debug_library = app / "AssociationProbe.debug.dylib"
    debug_entitlements = embedded_entitlements(debug_library) if debug_library.exists() else None
    print(json.dumps({"debug_library_entitlements_present": debug_entitlements is not None}), flush=True)
    print(json.dumps({"main_executable_entitlements_present": actual is not None,
                      "main_executable_identity_matches": actual is not None and actual.get("application-identifier") == expected["application-identifier"],
                      "main_executable_domains_match": actual is not None and actual.get("com.apple.developer.associated-domains") == expected["com.apple.developer.associated-domains"]}), flush=True)
    print("phase: simulator-creation", flush=True)
    runtime = "com.apple.CoreSimulator.SimRuntime.iOS-26-2"
    runtimes = json.loads(run(["xcrun", "simctl", "list", "runtimes", "--json"]))["runtimes"]
    if not any(r.get("identifier") == runtime and r.get("isAvailable") for r in runtimes):
        raise RuntimeError("Required simulator runtime unavailable.")
    udid = run(["xcrun", "simctl", "create", "Association probe", "com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation", runtime]).decode().strip()
    run(["xcrun", "simctl", "boot", udid])
    run(["xcrun", "simctl", "bootstatus", udid, "-b"])
    print("phase: install", flush=True)
    run(["xcrun", "simctl", "install", udid, str(app)])
    bundle = json.loads(os.environ["PROBE_CONFIG_JSON"])["APP_BUNDLE_ID"]
    environment = os.environ.copy()
    environment["SIMCTL_CHILD_PROBE_AUTOSTART"] = "1"
    print("phase: launch", flush=True)
    run(["xcrun", "simctl", "launch", udid, bundle], env=environment)
    container = Path(run(["xcrun", "simctl", "get_app_container", udid, bundle, "data"]).decode().strip())
    events_path = container / "Documents/probe-events.json"
    allowed = {"handler", "configuration_failure", "callback_received", "association_failure", "other_session_failure", "empty_completion", "start_accepted", "start_rejected", "key_window_present", "key_window_missing"}
    terminal = {"configuration_failure", "callback_received", "association_failure", "other_session_failure", "empty_completion", "start_rejected"}
    start = time.monotonic()
    seen = 0
    while time.monotonic() - start < 1000:
        if events_path.exists():
            events = json.loads(events_path.read_text())
            if not isinstance(events, list) or any(not isinstance(e, str) or e not in allowed for e in events):
                raise RuntimeError("Unexpected diagnostic content; output withheld.")
            for event in events[seen:]:
                print(json.dumps({"event": event, "observed_after_seconds": round(time.monotonic() - start, 1)}), flush=True)
            seen = len(events)
            if terminal.intersection(events):
                seal_evidence(udid)
                raise SystemExit(0 if "callback_received" in events else 1)
        time.sleep(2)
    seal_evidence(udid)
    print("INCONCLUSIVE: session did not complete; browser presentation is not verified.", flush=True)
    raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Do not expose subprocess output, URLs, identity, or file paths.
        print("Diagnostic infrastructure failed; private inspection is required.", flush=True)
        raise SystemExit(1)
