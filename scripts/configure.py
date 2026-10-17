"""Generate private runtime/build configuration without printing its values."""
import base64
import hashlib
import json
import secrets
import os
import plistlib
from pathlib import Path
from urllib.parse import urlencode, urlsplit
from urllib.request import urlopen

root = Path(__file__).resolve().parents[1]
try:
    values = json.loads(os.environ.get("PROBE_CONFIG_JSON", "{}"))
    names = ("ISSUER_URL", "CLIENT_ID", "CALLBACK_HOST", "CALLBACK_PATH", "APP_BUNDLE_ID", "APP_TEAM_ID")
    if not isinstance(values, dict) or any(not isinstance(values.get(name), str) or not values[name] for name in names):
        raise ValueError()
    if urlsplit(values["ISSUER_URL"]).scheme != "https" or not values["CALLBACK_PATH"].startswith("/"):
        raise ValueError()
    with urlopen(values["ISSUER_URL"].rstrip("/") + "/.well-known/openid-configuration", timeout=120) as response:
        discovery = json.load(response)
    endpoint = discovery["authorization_endpoint"]
    if urlsplit(endpoint).scheme != "https":
        raise ValueError()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(secrets.token_urlsafe(32).encode()).digest()).decode().rstrip("=")
    parameters = {"client_id": values["CLIENT_ID"], "redirect_uri": "https://" + values["CALLBACK_HOST"] + values["CALLBACK_PATH"],
                  "response_type": "code", "scope": "openid profile email", "prompt": "login",
                  "state": secrets.token_urlsafe(32), "nonce": secrets.token_urlsafe(32),
                  "code_challenge_method": "S256", "code_challenge": challenge}
    values["AUTHORIZATION_URL"] = endpoint + ("&" if "?" in endpoint else "?") + urlencode(parameters)
except Exception:
    raise SystemExit("Probe configuration or discovery failed; details withheld to protect endpoint configuration.")
private = root / ".generated"
private.mkdir(mode=0o700, exist_ok=True)
def plist(name, value):
    path = private / name
    path.write_bytes(plistlib.dumps(value))
    path.chmod(0o600)
plist("Runtime.plist", {"authorizationURL": values["AUTHORIZATION_URL"], "callbackHost": values["CALLBACK_HOST"], "callbackPath": values["CALLBACK_PATH"]})
plist("Info.plist", {"CFBundleExecutable": "$(EXECUTABLE_NAME)", "CFBundleIdentifier": "$(PRODUCT_BUNDLE_IDENTIFIER)", "CFBundleName": "AssociationProbe", "CFBundlePackageType": "APPL", "CFBundleShortVersionString": "1.0", "CFBundleVersion": "1", "UILaunchScreen": {}, "UIApplicationSceneManifest": {"UIApplicationSupportsMultipleScenes": False}})
plist("App.entitlements", {"application-identifier": values["APP_TEAM_ID"] + "." + values["APP_BUNDLE_ID"], "com.apple.developer.associated-domains": ["applinks:" + values["CALLBACK_HOST"], "webcredentials:" + values["CALLBACK_HOST"]]})
project = {"name": "AssociationProbe", "targets": {"AssociationProbe": {"type": "application", "platform": "iOS", "deploymentTarget": "17.4", "sources": ["App", {"path": ".generated/Runtime.plist", "buildPhase": "resources"}], "settings": {"base": {"PRODUCT_BUNDLE_IDENTIFIER": values["APP_BUNDLE_ID"], "INFOPLIST_FILE": ".generated/Info.plist", "CODE_SIGN_ENTITLEMENTS": ".generated/App.entitlements", "CODE_SIGN_IDENTITY": "-", "CODE_SIGNING_ALLOWED": "YES", "CODE_SIGNING_REQUIRED": "NO", "ENTITLEMENTS_ALLOWED": "YES", "SWIFT_VERSION": "5.0", "TARGETED_DEVICE_FAMILY": "1,2"}}}}}
# Keep the spec at the repository root so its relative source paths resolve there.
(root / ".generated-project.json").write_text(json.dumps(project))
(root / ".generated-project.json").chmod(0o600)
