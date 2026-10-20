"""Generic WireGuard/SSH/TLS probe; no application sources or cloud credentials."""
import json, os, pathlib, subprocess, time
root=pathlib.Path(os.environ['RUNNER_TEMP'])/'transport'
root.mkdir(mode=0o700,exist_ok=True)
phase=os.environ['PHASE']
slot=os.environ['SLOT']
def run(args,**kw):return subprocess.run(args,text=True,check=True,**kw)
if phase=='keys':
 config=json.loads(os.environ['PROBE'])
 print('::add-mask::'+config['endpoint'])
 private=run(['wg','genkey'],capture_output=True).stdout.strip()
 public=run(['wg','pubkey'],input=private,capture_output=True).stdout.strip()
 run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(root/'ssh')])
 (root/'public.json').write_text(json.dumps({'wireguard':public,'ssh':(root/'ssh.pub').read_text().strip()}))
 (root/'known_hosts').write_text('10.77.0.1 '+config['ssh_host_key']+'\n')
 (root/'probe.conf').write_text('[Interface]\nPrivateKey = '+private+'\nAddress = 10.77.0.'+slot+'/32\n[Peer]\nPublicKey = '+config['wireguard_public_key']+'\nEndpoint = '+config['endpoint']+':51820\nAllowedIPs = 10.77.0.1/32\nPersistentKeepalive = 25\n')
 (root/'probe.conf').chmod(0o600)
else:
 ssh=['ssh','-i',str(root/'ssh'),'-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(root/'known_hosts'),'-o','ConnectTimeout=10','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=2']
 # Registration is supplied externally; wait for readiness before executing each test once.
 end=time.monotonic()+600
 timeouts=0
 while time.monotonic()<end:
  try:
   p=subprocess.run(ssh+['probe@10.77.0.1','test -f /home/probe/ready'],capture_output=True,text=True,timeout=20)
   if p.returncode==0:break
  except subprocess.TimeoutExpired:timeouts+=1
  time.sleep(5)
 else:raise SystemExit('Registration/SSH readiness deadline exceeded')
 results={'readiness_command_timeouts':timeouts,'checks':[]}
 def check(name,args,timeout=90,output=None):
  start=time.monotonic()
  try:
   with open(output or os.devnull,'w') as out:
    p=subprocess.run(args,stdout=out,stderr=subprocess.PIPE,text=True,timeout=timeout)
   item={'name':name,'exit_code':p.returncode,'seconds':round(time.monotonic()-start,3),'stderr':p.stderr[-3000:]}
  except subprocess.TimeoutExpired as e:item={'name':name,'timeout':True,'seconds':round(time.monotonic()-start,3),'stderr':str(e.stderr or '')[-3000:]}
  results['checks'].append(item)
  (root/'results.json').write_text(json.dumps(results,indent=2))
  print(name, item.get('exit_code','timeout'), item['seconds'])
 check('ssh-small',ssh+['probe@10.77.0.1','printf ready'])
 check('ssh-large',ssh+['probe@10.77.0.1','cat /opt/probe/www/large.bin'])
 check('ca-transfer',ssh+['probe@10.77.0.1','cat /home/probe/root.crt'],output=root/'root.crt')
 check('forward',ssh+['-N','-f','-M','-S',str(root/'socket'),'-o','ExitOnForwardFailure=yes','-L','127.0.0.1:8443:127.0.0.1:443','probe@10.77.0.1'])
 for path in ('health','large.bin'):
  check('tls-'+path,['curl','--fail','--silent','--show-error','--max-time','120','--cacert',str(root/'root.crt'),'--resolve','probe.test:8443:127.0.0.1','https://probe.test:8443/'+path],timeout=125)
 check('server-mtu',ssh+['probe@10.77.0.1','cat /sys/class/net/wg0/mtu'],output=root/'server-mtu.txt')
 raise SystemExit(0 if all(x.get('exit_code')==0 for x in results['checks']) else 1)
