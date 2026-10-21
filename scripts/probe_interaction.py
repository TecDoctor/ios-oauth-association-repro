"""Build and test an original, credential-free UI on one disposable hosted simulator."""
import json
import os
from pathlib import Path
import plistlib
import signal
import subprocess
import time

if os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted':
    raise SystemExit('Disposable hosted runners only')
mode = os.environ['PROBE_PRESS']
assert mode in ('tap', 'long-press')
result = Path('results'); result.mkdir(exist_ok=True)
def run(args, timeout=600):
    return subprocess.check_output(args, text=True, timeout=timeout).strip()
devices = json.loads(run(['xcrun','simctl','list','devices','available','--json']))
device = next(d for runtime, items in devices['devices'].items() if runtime.endswith('iOS-27-0')
              for d in items if d['name'] == 'iPhone 17')
udid = device['udid']
if device['state'] != 'Booted':
    run(['xcrun','simctl','boot',udid])
run(['xcrun','simctl','bootstatus',udid,'-b'])
app = Path('.build/InteractionProbe.app'); app.mkdir(parents=True,exist_ok=True)
(app/'Info.plist').write_bytes(plistlib.dumps({
    'CFBundleIdentifier':'org.example.interactionprobe','CFBundleName':'InteractionProbe',
    'CFBundleExecutable':'InteractionProbe','CFBundlePackageType':'APPL',
    'CFBundleVersion':'1','CFBundleShortVersionString':'1.0',
    'MinimumOSVersion':'17.0','UIDeviceFamily':[1],'UILaunchScreen':{},
    'UIApplicationSceneManifest':{'UIApplicationSupportsMultipleScenes':False}}))
sdk=run(['xcrun','--sdk','iphonesimulator','--show-sdk-path'])
run(['xcrun','swiftc','-parse-as-library','-sdk',sdk,'-target','arm64-apple-ios17.0-simulator',
     'InteractionProbe/App.swift','-o',str(app/'InteractionProbe')])
run(['codesign','--force','--sign','-',str(app)])
run(['xcrun','simctl','install',udid,str(app)])
press = '- longPressOn:\n    id: probe.activate' if mode == 'long-press' else '- tapOn:\n    id: probe.activate\n    retryTapIfNoChange: false'
flow = result/'flow.yaml'
flow.write_text('''appId: org.example.interactionprobe
---
- launchApp
- scrollUntilVisible:
    element:
      id: probe.activate
    direction: DOWN
    timeout: 120000
    speed: 20
    visibilityPercentage: 100
    centerElement: true
- scrollUntilVisible:
    element:
      id: probe.activate
    direction: UP
    timeout: 120000
    speed: 20
    visibilityPercentage: 100
    centerElement: true
- waitForAnimationToEnd:
    timeout: 5000
- takeScreenshot: results/before-press
'''+press+'''
- takeScreenshot: results/after-press
- assertVisible: 'Handler count: 1'
''')
env={k:v for k,v in os.environ.items() if k in {'DEVELOPER_DIR','HOME','JAVA_HOME','LANG','LC_ALL','PATH','TMPDIR'}}
env.update(MAESTRO_CLI_NO_ANALYTICS='1',MAESTRO_DISABLE_UPDATE_CHECK='true',MAESTRO_CLI_ANALYSIS_NOTIFICATION_DISABLED='true')
binary=str(Path(os.environ['RUNNER_TEMP'])/'maestro/maestro/bin/maestro')
start=time.monotonic()
with (result/'maestro.log').open('w') as log:
    child=subprocess.Popen([binary,'--device',udid,'test','--debug-output',str(result/'debug'),'--test-output-dir',str(result/'debug'),str(flow)],
                           env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True)
    try:
        child.wait(timeout=900)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid,signal.SIGKILL);child.wait(timeout=15)
run(['xcrun','simctl','io',udid,'screenshot',str(result/'final.png')])
container=Path(run(['xcrun','simctl','get_app_container',udid,'org.example.interactionprobe','data']))
marker=container/'Documents/handler-count.txt'
count=marker.read_text() if marker.exists() else '0'
report={'press':mode,'handler_count':count,'exit_code':child.returncode,'elapsed_seconds':round(time.monotonic()-start,3)}
(result/'interaction.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
if child.returncode or count!='1':
    raise SystemExit(1)
