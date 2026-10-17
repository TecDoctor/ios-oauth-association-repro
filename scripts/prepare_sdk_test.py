"""Attach public UI tests to an independently built, private SDK sample app."""
import json
import os
import plistlib
from pathlib import Path


def prepare(source, sdk_app, destination, config, credentials):
    sdk_app = Path(sdk_app).resolve()
    info = plistlib.loads((sdk_app / "Info.plist").read_bytes())
    if info.get("CFBundleIdentifier") != config["APP_BUNDLE_ID"]:
        raise ValueError("SDK application identity does not match the configured test identity.")
    if any(not isinstance(credentials.get(k), str) or not credentials[k] for k in ("E2E_USERNAME", "E2E_PASSWORD")):
        raise ValueError("Sandbox credentials are incomplete.")
    specification = plistlib.loads(Path(source).read_bytes())
    if "TestConfigurations" in specification:
        targets = [target for configuration in specification["TestConfigurations"]
                   for target in configuration["TestTargets"]]
    else:
        targets = [value for key, value in specification.items() if not key.startswith("__")]
    if len(targets) != 1 or not targets[0].get("IsUITestBundle"):
        raise ValueError("Expected exactly one UI test target.")
    target = targets[0]
    previous = target["UITargetAppPath"]
    target["UITargetAppPath"] = str(sdk_app)
    target["DependentProductPaths"] = [str(sdk_app) if path == previous else path
                                       for path in target["DependentProductPaths"]]
    target["UITargetAppEnvironmentVariables"] = {}
    target.setdefault("EnvironmentVariables", {}).update({
        "SDK_APP_BUNDLE_ID": config["APP_BUNDLE_ID"],
        "SDK_USERNAME": credentials["E2E_USERNAME"],
        "SDK_PASSWORD": credentials["E2E_PASSWORD"],
    })
    # Keep the file beside the original so __TESTROOT__ references remain valid.
    destination = Path(destination)
    if destination.parent.resolve() != Path(source).parent.resolve():
        raise ValueError("The private test specification must retain its original test root.")
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as output:
        os.fchmod(output.fileno(), 0o600)
        plistlib.dump(specification, output)


if __name__ == "__main__":
    try:
        prepare(os.environ["PROBE_XCTESTRUN"], os.environ["SDK_APP_PATH"],
                os.environ["SDK_XCTESTRUN"], json.loads(os.environ["PROBE_CONFIG_JSON"]),
                json.loads(os.environ["SANDBOX_CREDENTIALS_JSON"]))
    except Exception:
        raise SystemExit("SDK test preparation failed; private configuration withheld.") from None
