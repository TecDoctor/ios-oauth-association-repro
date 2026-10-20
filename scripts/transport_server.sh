#!/bin/bash
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq wireguard-tools docker.io python3
useradd -m -s /bin/bash probe
install -d -m700 -o probe -g probe /home/probe/.ssh
install -d -m700 /etc/wireguard
umask 077
wg genkey > /etc/wireguard/key
ip link add wg0 type wireguard
ip addr add 10.77.0.1/24 dev wg0
wg set wg0 private-key /etc/wireguard/key listen-port 51820
ip link set wg0 up
printf 'PROBE_WG_KEY='; wg pubkey < /etc/wireguard/key
printf 'PROBE_SSH_KEY='; cat /etc/ssh/ssh_host_ed25519_key.pub
cat > /usr/local/sbin/probe-peers.py <<'PY'
import urllib.request,json,subprocess,pathlib,re
base='http://metadata.google.internal/computeMetadata/v1/instance/attributes/'
def read(p):
 with urllib.request.urlopen(urllib.request.Request(base+p,headers={'Metadata-Flavor':'Google'}),timeout=10) as r:return r.read().decode()
keys=[]
for name in read('').splitlines():
 if re.fullmatch('probe-peer-[234]',name):
  item=json.loads(read(name));slot=int(name[-1])
  assert re.fullmatch('[A-Za-z0-9+/]{43}=',item['wireguard'])
  assert re.fullmatch(r'ssh-ed25519 [A-Za-z0-9+/]+(?: [^\r\n]*)?',item['ssh'])
  subprocess.run(['wg','set','wg0','peer',item['wireguard'],'allowed-ips',f'10.77.0.{slot}/32'],check=True)
  keys.append(item['ssh'])
p=pathlib.Path('/home/probe/.ssh/authorized_keys');p.write_text('\n'.join(keys)+'\n');p.chmod(0o600)
subprocess.run(['chown','probe:probe',str(p)],check=True)
PY
cat > /etc/systemd/system/probe-peers.service <<'UNIT'
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/sbin/probe-peers.py
UNIT
cat > /etc/systemd/system/probe-peers.timer <<'UNIT'
[Timer]
OnBootSec=5s
OnUnitActiveSec=5s
[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now probe-peers.timer docker
mkdir -p /opt/probe/www
head -c 1048576 /dev/urandom > /opt/probe/www/large.bin
printf 'healthy\n' > /opt/probe/www/health
cat > /opt/probe/Caddyfile <<'CADDY'
https://probe.test {
 tls internal
 root * /srv
 file_server
}
CADDY
docker run -d --name probe-tls -p 127.0.0.1:443:443 -v /opt/probe/Caddyfile:/etc/caddy/Caddyfile:ro -v /opt/probe/www:/srv:ro caddy:2
for n in $(seq 1 60); do
 if docker cp probe-tls:/data/caddy/pki/authorities/local/root.crt /home/probe/root.crt; then chmod 644 /home/probe/root.crt; touch /home/probe/ready; echo PROBE_READY; exit 0; fi
 sleep 2
done
exit 1
