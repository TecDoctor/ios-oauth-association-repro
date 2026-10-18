"""Build the private SDK sample and run the public UI-only sandbox test in CI."""
import json
import os
import subprocess
from pathlib import Path

import run_probe as probe
from prepare_sdk_test import prepare


def private_command(arguments, name, cwd=None, environment=None, timeout=1800):
    output = probe.BUILD / ("private-" + name + ".log")
    with output.open("wb") as log:
        result = subprocess.run(arguments, cwd=cwd, env=environment,
                                stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode:
        raise RuntimeError("Private SDK preparation failed.")


def main():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("This runner is restricted to disposable GitHub Actions VMs.")
    config = json.loads(os.environ["PROBE_CONFIG_JSON"])
    credentials = json.loads(os.environ["SANDBOX_CREDENTIALS_JSON"])
    sdk = probe.ROOT / "sdk-private"
    scripts = sdk / "health-portal-sdk/Scripts"
    print("phase: private-sdk-model-generation", flush=True)
    npm = probe.BUILD / "generator"
    private_command(["npm", "install", "--prefix", str(npm),
                     "@openapitools/openapi-generator-cli@2.41.0"], "generator-install")
    binary = probe.BUILD / "bin"
    binary.mkdir(exist_ok=True)
    (binary / "openapi-generator").symlink_to(npm / "node_modules/.bin/openapi-generator-cli")
    environment = os.environ.copy()
    environment["PATH"] = str(binary) + os.pathsep + environment["PATH"]
    private_command(["bash", "generate-models.sh", "--skip-xcode"], "models", scripts, environment)
    print("phase: private-sdk-build", flush=True)
    derived = probe.BUILD / "sdk-build"
    private_command(["xcodebuild", "-project", str(sdk / "Samples/SampleApp/SampleApp.xcodeproj"),
                     "-scheme", "Sandbox", "-configuration", "Sandbox", "-sdk", "iphonesimulator",
                     "-destination", "generic/platform=iOS Simulator", "-derivedDataPath", str(derived),
                     "-clonedSourcePackagesDirPath", str(probe.BUILD / "packages"),
                     "-onlyUsePackageVersionsFromResolvedFile", "ARCHS=arm64", "ONLY_ACTIVE_ARCH=YES",
                     "CODE_SIGN_IDENTITY=-", "ENTITLEMENTS_ALLOWED=YES", "-jobs", "2", "build"], "sdk-build")
    app = derived / "Build/Products/Sandbox-iphonesimulator/SampleApp.app"
    print("phase: ui-test-build", flush=True)
    probe.run(["xcodegen", "generate", "--spec", ".generated-project.json"])
    probe.run(["xcodebuild", "-project", "AssociationProbe.xcodeproj", "-scheme", "AssociationProbe",
               "-sdk", "iphonesimulator", "-destination", "generic/platform=iOS Simulator",
               "-derivedDataPath", str(probe.BUILD), "ARCHS=arm64", "ONLY_ACTIVE_ARCH=YES",
               "-jobs", "2", "build-for-testing"])
    products = probe.BUILD / "Build/Products"
    originals = list(products.glob("*.xctestrun"))
    if len(originals) != 1:
        raise RuntimeError("Expected one generated UI test specification.")
    specification = products / "SDK-private.xctestrun"
    prepare(originals[0], app, specification, config, credentials)
    print("phase: isolated-ci-simulator", flush=True)
    runtime = "com.apple.CoreSimulator.SimRuntime.iOS-26-2"
    udid = probe.run(["xcrun", "simctl", "create", "SDK sandbox test",
                      "com.apple.CoreSimulator.SimDeviceType.iPhone-SE-3rd-generation", runtime]).decode().strip()
    probe.run(["xcrun", "simctl", "boot", udid])
    probe.run(["xcrun", "simctl", "bootstatus", udid, "-b"])
    probe.run(["xcrun", "simctl", "install", udid, str(app)])
    container = Path(probe.run(["xcrun", "simctl", "get_app_container", udid,
                                config["APP_BUNDLE_ID"], "data"]).decode().strip())
    try:
        print("phase: sdk-sandbox-login-logout", flush=True)
        probe.run(["xcodebuild", "test-without-building", "-xctestrun", str(specification),
                   "-destination", "id=" + udid, "-parallel-testing-enabled", "NO",
                   "-maximum-concurrent-test-simulator-destinations", "1",
                   "-resultBundlePath", str(probe.BUILD / "BrowserResult.xcresult"),
                   "-only-testing:ProbeUITests/SDKAuthenticationTests/testSandboxLoginLogout"], timeout=3000)
        print("SDK sandbox login, logout and logout persistence passed.", flush=True)
    finally:
        probe.seal_evidence(udid, container)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        if not (probe.BUILD / "diagnostics.enc").exists():
            try:
                probe.seal_evidence(None, None)
            except Exception:
                pass
        print("SDK sandbox verification failed; raw private output withheld.", flush=True)
        raise SystemExit(1)
