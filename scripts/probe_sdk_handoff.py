"""One SDK handoff observation; private checkout/output never becomes public artifacts."""
import json
import os
import plistlib
import re
from pathlib import Path
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / '.build'
EVIDENCE = BUILD / 'private-evidence'
RUNTIME_CONTEXT = {}
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


def capture_association(udid, executable, name):
    if executable is None:
        return False
    try:
        run(['xcrun', 'simctl', 'spawn', udid, str(executable), 'show'], name, timeout=120)
        return True
    except (RuntimeError, subprocess.TimeoutExpired):
        # Optional diagnostics must not prevent the one functional execution.
        return False


def associations_approved(text, identity, domains):
    approved = set()
    for block in text.split('--------------------------------------------------------------------------------'):
        fields = {}
        for line in block.splitlines():
            key, separator, value = line.partition(':')
            if separator:
                fields[key.strip()] = value.strip()
        if (fields.get('Service') == 'webcredentials' and fields.get('App ID') == identity
                and fields.get('Site/Fmwk Approval') == 'approved'):
            # The OS keeps this retrieval-mode suffix in its approved record.
            approved.add(fields.get('Domain', '').removesuffix('?mode=developer'))
    return bool(domains) and set(domains) <= approved


def wait_for_associations(udid, executable, identity, domains, timeout=1000):
    if executable is None:
        raise RuntimeError('Association readiness tool unavailable')
    started = time.monotonic()
    while time.monotonic() - started < timeout:
        # Observe OS registration only. Never add, approve, reset, or retry authentication.
        remaining = max(1, int(timeout - (time.monotonic() - started)))
        state = run(['xcrun', 'simctl', 'spawn', udid, str(executable), 'show'],
                    'association-readiness', timeout=min(30, remaining)).decode()
        if associations_approved(state, identity, domains):
            elapsed = round(time.monotonic() - started, 3)
            print(json.dumps({'association_ready_seconds': elapsed}), flush=True)
            return elapsed
        time.sleep(min(5, max(0, timeout - (time.monotonic() - started))))
    raise RuntimeError('OS association did not become approved before authentication')


def observe_execution(child, events_path, timeout=3000):
    deadline = time.monotonic() + timeout
    seen = 0
    terminal = None
    while child.poll() is None and time.monotonic() < deadline:
        try:
            events = json.loads(events_path.read_text()) if events_path.stat().st_size <= 65536 else []
        except (OSError, ValueError):
            events = []
        if isinstance(events, list):
            for item in events[seen:]:
                event = item.get('event') if isinstance(item, dict) else None
                if event in ALLOWED_EVENTS:
                    print(json.dumps({'observed_event': event}), flush=True)
                if event in {'login.failure', 'logout.failure'}:
                    terminal = event
            seen = max(seen, len(events))
        if terminal:
            break
        time.sleep(2)
    if child.poll() is None:
        terminal = terminal or 'execution-timeout'
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            child.wait(timeout=15)
    return terminal


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
    diagnostics_required = os.environ.pop('EXPECT_SDK_DIAGNOSTICS', 'false') == 'true'
    target = os.environ.pop('PROBE_TARGET', 'sandbox')
    if target not in {'sandbox', 'docker'}:
        raise RuntimeError('Unsupported probe target')
    sandbox = os.environ.pop('SANDBOX_CREDENTIALS_JSON', '')
    remote = os.environ.pop('REMOTE_PROBE_JSON', '')
    credentials = json.loads(sandbox) if target == 'sandbox' else json.loads(remote)['account']
    configuration = 'Sandbox' if target == 'sandbox' else 'Local'
    if any(not isinstance(credentials.get(key), str) or not credentials[key]
           for key in ('E2E_USERNAME', 'E2E_PASSWORD')):
        raise RuntimeError('Probe account configuration missing')
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
    entitlements = plistlib.loads((sdk / f'Samples/SampleApp/SampleApp/SampleApp{configuration}.entitlements').read_bytes())
    run(['xcodebuild', '-project', str(sdk / 'Samples/SampleApp/SampleApp.xcodeproj'),
         '-scheme', configuration, '-configuration', configuration, '-sdk', 'iphonesimulator',
         '-destination', 'generic/platform=iOS Simulator', '-derivedDataPath', str(derived),
         '-clonedSourcePackagesDirPath', str(BUILD / 'packages'),
         '-onlyUsePackageVersionsFromResolvedFile', 'ARCHS=arm64', 'ONLY_ACTIVE_ARCH=YES',
         'CODE_SIGN_IDENTITY=-', 'ENTITLEMENTS_ALLOWED=YES', '-jobs', '2', 'build'], 'build')
    app = derived / f'Build/Products/{configuration}-iphonesimulator/SampleApp.app'
    from run_probe import embedded_entitlements
    actual = embedded_entitlements(app / 'SampleApp')
    (EVIDENCE / 'embedded-entitlements.plist').write_bytes(plistlib.dumps(actual or {}))
    expected = {'application-identifier': team + '.' + bundle,
                'com.apple.developer.associated-domains': entitlements['com.apple.developer.associated-domains']}
    if any((actual or {}).get(key) != value for key, value in expected.items()):
        raise RuntimeError('Finished executable identity differs from requested identity')
    run(['codesign', '-d', '--entitlements', ':-', str(app)], 'codesign-entitlements')
    devices = json.loads(run(['xcrun', 'simctl', 'list', 'devices', 'available', '--json'], 'devices'))
    device = next(d for runtime, items in devices['devices'].items() if runtime.endswith('iOS-27-0')
                  for d in items if d['name'] == 'iPhone 17')
    udid = device['udid']
    RUNTIME_CONTEXT['udid'] = udid
    if device['state'] != 'Booted':
        run(['xcrun', 'simctl', 'boot', udid], 'boot')
    run(['xcrun', 'simctl', 'bootstatus', udid, '-b'], 'bootstatus', timeout=900)
    if target == 'docker':
        from remote_sdk_client import connect
        connect(diagnostics=EVIDENCE)
    run(['xcrun', 'simctl', 'install', udid, str(app)], 'install')
    association_tool = None
    try:
        runtimes = json.loads(run(['xcrun', 'simctl', 'list', 'runtimes', '--json'], 'runtimes'))
        runtime = next(r for r in runtimes['runtimes'] if r['identifier'].endswith('iOS-27-0'))
        candidate = Path(runtime['bundlePath']) / 'Contents/Resources/RuntimeRoot/System/Library/PrivateFrameworks/SharedWebCredentials.framework/Support/swcutil'
        if candidate.is_file():
            association_tool = candidate
    except (RuntimeError, subprocess.TimeoutExpired, KeyError, StopIteration, ValueError):
        pass
    association_before = capture_association(udid, association_tool, 'association-before-login')
    run(['xcrun', 'simctl', 'launch', udid, bundle], 'launch-before-readiness', timeout=120)
    domains = [value.removeprefix('webcredentials:').split('?', 1)[0] for value in
               entitlements['com.apple.developer.associated-domains'] if value.startswith('webcredentials:')]
    association_seconds = wait_for_associations(udid, association_tool, team + '.' + bundle, domains)
    container = Path(run(['xcrun', 'simctl', 'get_app_container', udid,
                          'sample.HealthPortalSDKSampleApp', 'data'], 'container').decode().strip())
    events_path = container / 'Library/Caches/e2e-oauth-events.json'
    flow = EVIDENCE / 'flow.yaml'
    flow.write_text('''appId: sample.HealthPortalSDKSampleApp
---
- assertTrue: ${typeof MAESTRO_E2E_USERNAME === 'string' && MAESTRO_E2E_USERNAME.length > 0 && MAESTRO_E2E_USERNAME !== 'undefined'}
- assertTrue: ${typeof MAESTRO_E2E_PASSWORD === 'string' && MAESTRO_E2E_PASSWORD.length > 0 && MAESTRO_E2E_PASSWORD !== 'undefined'}
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
- tapOn:
    text: 'Continue|続ける'
    retryTapIfNoChange: false
- extendedWaitUntil:
    visible: 'Email input|Username or email input|Eメール入力欄|Eメール|メールアドレス入力欄'
    timeout: 1000000
- tapOn:
    text: 'Email input|Username or email input|Eメール入力欄|Eメール|メールアドレス入力欄'
    retryTapIfNoChange: false
- eraseText
- inputText: ${MAESTRO_E2E_USERNAME}
- tapOn:
    text: 'Next|次へ'
    retryTapIfNoChange: false
- tapOn:
    text: 'Password input|パスワード入力欄|パスワード'
    retryTapIfNoChange: false
- eraseText
- inputText: ${MAESTRO_E2E_PASSWORD}
- tapOn:
    text: 'Done|完了'
    retryTapIfNoChange: false
- scrollUntilVisible:
    element: 'Log In|Sign In|ログイン'
    direction: DOWN
    timeout: 120000
    visibilityPercentage: 100
    centerElement: true
- takeScreenshot: .build/private-evidence/before-web-submit
- tapOn:
    text: 'Log In|Sign In|ログイン'
    retryTapIfNoChange: false
# The callback may dismiss Safari before the optional password-save query.
- waitForAnimationToEnd:
    timeout: 60000
- takeScreenshot: .build/private-evidence/after-login-transition
- tapOn:
    text: 'Not Now|今はしない'
    optional: true
    retryTapIfNoChange: false
# A newly created disposable account can require its first-use consent.
- extendedWaitUntil:
    visible: 'OAuthでログイン|.*利用規約への同意|.*同意して登録する.*|.*についての同意'
    timeout: 1000000
- runFlow:
    when:
      visible: '.*利用規約への同意|.*同意して登録する.*'
    commands:
      - scrollUntilVisible:
          element: '個人情報の取扱いについて'
          direction: DOWN
          timeout: 450000
          centerElement: true
      - tapOn:
          text: '.*同意して登録する'
          enabled: true
          retryTapIfNoChange: false
      - waitForAnimationToEnd:
          timeout: 60000
# Each iteration accepts a different consent document, never repeats login.
- repeat:
    times: 5
    while:
      visible: '.*についての同意'
    commands:
      - scrollUntilVisible:
          element: '^同意する$'
          direction: DOWN
          timeout: 120000
      - tapOn:
          text: '^同意する$'
          enabled: true
          retryTapIfNoChange: false
      - waitForAnimationToEnd:
          timeout: 60000
- extendedWaitUntil:
    visible:
      id: sample.oauth.login
    timeout: 1000000
- scrollUntilVisible:
    element: '^ログイン済み$'
    direction: UP
    timeout: 120000
    visibilityPercentage: 100
- assertVisible: '^ログイン済み$'
- takeScreenshot: .build/private-evidence/authenticated
- scrollUntilVisible:
    element:
      id: sample.oauth.logout
    direction: DOWN
    timeout: 120000
    visibilityPercentage: 100
    centerElement: true
- tapOn:
    id: sample.oauth.logout
    retryTapIfNoChange: false
- tapOn:
    text: 'Continue|続ける'
    optional: true
    retryTapIfNoChange: false
# Avoid querying accessibility during Safari's dismissal transition.
# This observes screen stability; it does not repeat logout or restart the driver.
- waitForAnimationToEnd:
    timeout: 60000
- takeScreenshot: .build/private-evidence/after-logout-transition
- scrollUntilVisible:
    element: '^未ログイン$'
    direction: UP
    timeout: 120000
    visibilityPercentage: 100
- assertVisible: '^未ログイン$'
- assertNotVisible: '^ログイン済み$'
- takeScreenshot: .build/private-evidence/logged-out
- stopApp
- launchApp
- assertVisible: '^未ログイン$'
- assertNotVisible: '^ログイン済み$'
- takeScreenshot: .build/private-evidence/logout-persisted
''')
    clean_env = {k:v for k,v in env.items() if k in {'DEVELOPER_DIR','HOME','JAVA_HOME','LANG','LC_ALL','PATH','TMPDIR'}}
    clean_env.update({'MAESTRO_' + key: credentials[key] for key in ('E2E_USERNAME', 'E2E_PASSWORD')})
    clean_env.update(MAESTRO_CLI_NO_ANALYTICS='1', MAESTRO_DISABLE_UPDATE_CHECK='true',
                     MAESTRO_CLI_ANALYSIS_NOTIFICATION_DISABLED='true')
    maestro = str(Path(os.environ['RUNNER_TEMP']) / 'maestro/maestro/bin/maestro')
    print('phase: one-native-login-tap', flush=True)
    with (EVIDENCE / 'maestro.log').open('wb') as log:
        child = subprocess.Popen([maestro, '--device', udid, 'test', '--debug-output', str(EVIDENCE / 'debug'),
                                  '--test-output-dir', str(EVIDENCE / 'debug'), str(flow)],
                                 env=clean_env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        terminal_event = observe_execution(child, events_path)
    association_after = capture_association(udid, association_tool, 'association-after-login')
    run(['xcrun', 'simctl', 'io', udid, 'screenshot', str(EVIDENCE / 'final.png')], 'screenshot', timeout=120)
    events = json.loads(events_path.read_text()) if events_path.exists() else []
    if not isinstance(events, list):
        raise RuntimeError('Unexpected diagnostic schema')
    if events_path.exists():
        shutil.copyfile(events_path, EVIDENCE / 'sdk-events.json')
    safe = [e['event'] for e in events if isinstance(e, dict) and e.get('event') in ALLOWED_EVENTS]
    instrumented = bool(events)
    accepted = (terminal_event is None and child.returncode == 0
                and (not diagnostics_required or instrumented) and (not instrumented or
                all(safe.count(event) == 1 for event in
                    ('login.handler', 'login.success', 'logout.handler', 'logout.success'))))
    report = {'target': target, 'association_ready_seconds': association_seconds, 'terminal_event': terminal_event, 'association_capture_before': association_before, 'association_capture_after': association_after,
              'sdk_diagnostics_present': instrumented, 'events': safe,
              'handler_count': safe.count('login.handler') if instrumented else None,
              'discovery_started': 'discovery.start' in safe if instrumented else None,
              'discovery_completed': 'discovery.success' in safe if instrumented else None,
              'full_login_logout_passed': accepted, 'maestro_exit': child.returncode}
    print(json.dumps(report), flush=True)
    (EVIDENCE / 'summary.json').write_text(json.dumps(report))
    return 0 if accepted else 1


if __name__ == '__main__':
    status = 1
    try:
        status = main()
    except Exception as error:
        if EVIDENCE.exists():
            (EVIDENCE / 'failure.json').write_text(json.dumps(
                {'type': type(error).__name__, 'message': str(error)[:4096]}))
            if RUNTIME_CONTEXT.get('udid'):
                try:
                    run(['xcrun', 'simctl', 'io', RUNTIME_CONTEXT['udid'], 'screenshot',
                         str(EVIDENCE / 'failure.png')], 'failure-screenshot', timeout=30)
                except Exception:
                    pass
        print('Probe failed; private details withheld.', flush=True)
    finally:
        if EVIDENCE.exists():
            seal()
    raise SystemExit(status)
