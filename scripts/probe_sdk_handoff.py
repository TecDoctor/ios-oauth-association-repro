"""One SDK handoff observation; private checkout/output never becomes public artifacts."""
import json
import os
import plistlib
import re
from pathlib import Path
import shutil
import signal
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / '.build'
EVIDENCE = BUILD / 'private-evidence'
ALLOWED_EVENTS = {'configured', 'login.handler', 'login.success', 'login.failure',
                  'discovery.start', 'discovery.success', 'discovery.failure',
                  'session.request', 'session.start', 'session.failure', 'session.callback',
                  'session.anchor', 'logout.handler', 'logout.success', 'logout.failure'}


def run(args, name, *, cwd=ROOT, env=None, timeout=1800):
    with (EVIDENCE / (name + '.log')).open('wb') as log:
        result = subprocess.run(args, cwd=cwd, env=env, stdout=log,
                                stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, timeout=timeout)
    if result.returncode:
        raise RuntimeError('Private command failed; encrypted evidence only')
    return (EVIDENCE / (name + '.log')).read_bytes()


def seal():
    archive = shutil.make_archive(str(BUILD / 'private-diagnostics'), 'zip', EVIDENCE)
    try:
        subprocess.run(['openssl', 'cms', '-encrypt', '-binary', '-aes256', '-in', archive,
                        '-outform', 'DER', '-out', str(BUILD / 'diagnostics.enc'),
                        str(ROOT / 'diagnostics/recipient.pem')], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=120)
    finally:
        Path(archive).unlink(missing_ok=True)


def main():
    if os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
        raise RuntimeError('Disposable hosted runner required')
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    sdk = ROOT / 'sdk-private'
    env = os.environ.copy()
    print('phase: private-model-generation', flush=True)
    generator = BUILD / 'generator'
    run(['npm', 'install', '--prefix', str(generator), '@openapitools/openapi-generator-cli@2.41.0'], 'generator')
    binary = BUILD / 'bin'; binary.mkdir()
    (binary / 'openapi-generator').symlink_to(generator / 'node_modules/.bin/openapi-generator-cli')
    env['PATH'] = str(binary) + os.pathsep + env['PATH']
    run(['bash', 'generate-models.sh', '--skip-xcode'], 'models',
        cwd=sdk / 'health-portal-sdk/Scripts', env=env)
    print('phase: private-sdk-build', flush=True)
    derived = BUILD / 'sdk-build'
    # Diagnostic build preserves the project's identity without editing private source.
    project = sdk / 'Samples/SampleApp/SampleApp.xcodeproj/project.pbxproj'
    project_text = project.read_text()
    teams = set(re.findall(r'DEVELOPMENT_TEAM\s*=\s*([A-Z0-9]+);', project_text))
    bundles = set(re.findall(r'PRODUCT_BUNDLE_IDENTIFIER\s*=\s*([A-Za-z0-9_.-]+);', project_text))
    if len(teams) != 1 or len(bundles) != 1:
        raise RuntimeError('Ambiguous project identity')
    team, bundle = next(iter(teams)), next(iter(bundles))
    entitlements = plistlib.loads((sdk / 'Samples/SampleApp/SampleApp/SampleAppSandbox.entitlements').read_bytes())
    for key, value in {'application-identifier': team + '.' + bundle,
                       'com.apple.developer.team-identifier': team}.items():
        if key in entitlements and entitlements[key] != value:
            raise RuntimeError('Conflicting project identity')
        entitlements[key] = value
    entitlement_path = EVIDENCE / 'build.entitlements'
    entitlement_path.write_bytes(plistlib.dumps(entitlements))
    run(['xcodebuild', '-project', str(sdk / 'Samples/SampleApp/SampleApp.xcodeproj'),
         '-scheme', 'Sandbox', '-configuration', 'Sandbox', '-sdk', 'iphonesimulator',
         '-destination', 'generic/platform=iOS Simulator', '-derivedDataPath', str(derived),
         '-clonedSourcePackagesDirPath', str(BUILD / 'packages'),
         '-onlyUsePackageVersionsFromResolvedFile', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
         'CODE_SIGN_IDENTITY=-', 'ENTITLEMENTS_ALLOWED=YES',
         'CODE_SIGN_ENTITLEMENTS=' + str(entitlement_path), '-jobs', '2', 'build'], 'build')
    app = derived / 'Build/Products/Sandbox-iphonesimulator/SampleApp.app'
    from run_probe import embedded_entitlements
    actual = embedded_entitlements(app / 'SampleApp')
    (EVIDENCE / 'embedded-entitlements.plist').write_bytes(plistlib.dumps(actual or {}))
    if any((actual or {}).get(key) != entitlements[key] for key in
           ('application-identifier', 'com.apple.developer.team-identifier',
            'com.apple.developer.associated-domains')):
        raise RuntimeError('Finished executable identity differs from requested identity')
    run(['codesign', '-d', '--entitlements', ':-', str(app)], 'codesign-entitlements')
    devices = json.loads(run(['xcrun', 'simctl', 'list', 'devices', 'available', '--json'], 'devices'))
    device = next(d for runtime, items in devices['devices'].items() if runtime.endswith('iOS-27-0')
                  for d in items if d['name'] == 'iPhone 17')
    udid = device['udid']
    if device['state'] != 'Booted':
        run(['xcrun', 'simctl', 'boot', udid], 'boot')
    run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], 'bootstatus', timeout=900)
    run(['xcrun', 'simctl', 'install', udid, str(app)], 'install')
    flow = EVIDENCE / 'flow.yaml'
    flow.write_text('''appId: sample.HealthPortalSDKSampleApp
---
- launchApp
- scrollUntilVisible:
    element:
      id: sample.oauth.login
    direction: DOWN
    timeout: 120000
    speed: 20
    visibilityPercentage: 100
    centerElement: true
- scrollUntilVisible:
    element:
      id: sample.oauth.login
    direction: UP
    timeout: 120000
    speed: 20
    visibilityPercentage: 100
    centerElement: true
- waitForAnimationToEnd:
    timeout: 60000
- takeScreenshot: .build/private-evidence/before-press
- tapOn:
    id: sample.oauth.login
    enabled: true
    retryTapIfNoChange: false
- extendedWaitUntil:
    visible: 'Continue|続ける'
    timeout: 120000
''')
    clean_env = {k:v for k,v in env.items() if k in {'DEVELOPER_DIR','HOME','JAVA_HOME','LANG','LC_ALL','PATH','TMPDIR'}}
    clean_env.update(MAESTRO_CLI_NO_ANALYTICS='1', MAESTRO_DISABLE_UPDATE_CHECK='true',
                     MAESTRO_CLI_ANALYSIS_NOTIFICATION_DISABLED='true')
    maestro = str(Path(os.environ['RUNNER_TEMP']) / 'maestro/maestro/bin/maestro')
    print('phase: one-native-login-tap', flush=True)
    with (EVIDENCE / 'maestro.log').open('wb') as log:
        child = subprocess.Popen([maestro, '--device', udid, 'test', '--debug-output', str(EVIDENCE / 'debug'),
                                  '--test-output-dir', str(EVIDENCE / 'debug'), str(flow)],
                                 env=clean_env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        try:
            child.wait(timeout=1200)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=15)
    run(['xcrun', 'simctl', 'io', udid, 'screenshot', str(EVIDENCE / 'final.png')], 'screenshot', timeout=120)
    container = Path(run(['xcrun', 'simctl', 'get_app_container', udid,
                          'sample.HealthPortalSDKSampleApp', 'data'], 'container').decode().strip())
    events_path = container / 'Library/Caches/e2e-oauth-events.json'
    events = json.loads(events_path.read_text()) if events_path.exists() else []
    if not isinstance(events, list):
        raise RuntimeError('Unexpected diagnostic schema')
    if events_path.exists():
        shutil.copyfile(events_path, EVIDENCE / 'sdk-events.json')
    safe = [e['event'] for e in events if isinstance(e, dict) and e.get('event') in ALLOWED_EVENTS]
    report = {'events': safe, 'handler_count': safe.count('login.handler'),
              'discovery_started': 'discovery.start' in safe,
              'discovery_completed': 'discovery.success' in safe,
              'continue_assertion_passed': child.returncode == 0, 'maestro_exit': child.returncode}
    print(json.dumps(report), flush=True)
    (EVIDENCE / 'summary.json').write_text(json.dumps(report))
    return 0 if child.returncode == 0 else 1


if __name__ == '__main__':
    status = 1
    try:
        status = main()
    except Exception:
        print('Probe failed; private details withheld.', flush=True)
    finally:
        if EVIDENCE.exists():
            seal()
    raise SystemExit(status)
