"""Execute private owner tasks without publishing their source or outputs."""
import json,os,pathlib,platform,shlex,subprocess,time
root=pathlib.Path(os.environ['RUNNER_TEMP'])/'transport'
results=[]
def checked(name,args,timeout=120):
 start=time.monotonic()
 p=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
 results.append({'check':name,'exit_code':p.returncode,'seconds':round(time.monotonic()-start,3)})
 (root/'owner-results.json').write_text(json.dumps(results,indent=2))
 print(name, 'passed' if p.returncode==0 else 'failed',flush=True)
 if p.returncode:raise SystemExit(p.returncode)
 return p.stdout
ssh=['ssh','-i',str(root/'ssh'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(root/'known_hosts'),'-o','ConnectTimeout=20']
checked('close baseline forward',ssh+['-S',str(root/'socket'),'-O','exit','probe@10.77.0.1'])
checked('owner redirect setup',['make','-s','-C','private-owner','caddy.forward.setup'])
(root/'redirect-installed').touch()
forward=ssh+['-N','-f','-M','-S',str(root/'owner-socket'),'-o','ExitOnForwardFailure=yes','-L','127.0.0.1:8443:127.0.0.1:443']
checked('owner forward',['make','-s','-C','private-owner','caddy.forward','CADDY_SSH_HOST=probe@10.77.0.1','CADDY_FORWARD_COMMAND='+shlex.join(forward)])
checked('HTTPS through port 443',['curl','--fail','--silent','--show-error','--max-time','120','--cacert',str(root/'root.crt'),'--resolve','probe.test:443:127.0.0.1','https://probe.test/health'])
if platform.system()=='Darwin':
 checked('owner macOS CA trust',['make','-s','-C','private-owner','-o','caddy.download','-o','caddy.untrust.mac','caddy.trust.mac','CADDY_CERTIFICATE_PATH='+str(root/'root.crt')])
 data=json.loads(checked('list simulator inventory',['xcrun','simctl','list','devices','available','--json']))
 devices=[d for runtime,ds in data['devices'].items() if runtime.endswith('iOS-27-0') for d in ds if d['name']=='iPhone 17']
 if not devices:raise SystemExit('Bundled iPhone 17 / iOS 27 unavailable; no runtime download or alternate device')
 device=devices[0];udid=device['udid']
 if device['state']!='Booted':checked('boot selected hosted simulator',['xcrun','simctl','boot',udid])
 checked('wait for hosted simulator boot',['xcrun','simctl','bootstatus',udid,'-b'],timeout=600)
 checked('owner simulator CA trust',['make','-s','-C','private-owner','-o','caddy.download','caddy.trust.iossim','CADDY_CERTIFICATE_PATH='+str(root/'root.crt')])
 checked('set disposable runner hosts',['sudo','sh','-c',"printf '\n127.0.0.1 probe.test\n' >> /etc/hosts"])
 sdk=checked('locate bundled simulator SDK',['xcrun','--sdk','iphonesimulator','--show-sdk-path']).strip()
 checked('compile generic native HTTPS probe',['xcrun','--sdk','iphonesimulator','swiftc','-sdk',sdk,'-target','arm64-apple-ios27.0-simulator','scripts/native_https.swift','-o',str(root/'native-https')],timeout=180)
 native=checked('assert native iOS HTTPS response',['xcrun','simctl','spawn',udid,str(root/'native-https')],timeout=210)
 (root/'native-https.json').write_text(native)
 checked('launch Safari before single navigation',['xcrun','simctl','launch',udid,'com.apple.mobilesafari'],timeout=120)
 checked('open synthetic HTTPS in Safari',['xcrun','simctl','openurl',udid,'https://probe.test/health'])
 time.sleep(60)
 checked('capture Safari evidence',['xcrun','simctl','io',udid,'screenshot',str(root/'safari-https.png')],timeout=120)
 print('Safari screenshot requires visual inspection; openurl success alone is not certificate acceptance.',flush=True)
