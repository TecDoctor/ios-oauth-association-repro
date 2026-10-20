"""Generic TLS byte forwarding for disposable public CI; no cloud credentials."""
import asyncio
import ipaddress
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.parse import urlsplit
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = ROOT / ".generated"


def prepare():
    if os.environ.get("GITHUB_ACTIONS") != "true":
        raise RuntimeError("Disposable CI only")
    config = json.loads(os.environ["REMOTE_PROBE_JSON"])
    ipaddress.IPv4Address(config["address"])
    PRIVATE.mkdir(mode=0o700, exist_ok=True)
    (PRIVATE / "remote.json").write_text(json.dumps(config))
    (PRIVATE / "remote.json").chmod(0o600)
    certificate = PRIVATE / "root.crt"
    certificate.write_text(config["ca"])
    certificate.chmod(0o600)
    with urlopen("https://api.ipify.org", timeout=30) as response:
        address = str(ipaddress.IPv4Address(response.read().decode().strip()))
    (ROOT / "runner-ip.txt").write_text(address + "\n")


async def serve(config, uid, gid):
    async def handle(reader, writer):
        try:
            upstream, remote = await asyncio.wait_for(asyncio.open_connection(config["address"], 8443), 30)
            async def pipe(source, destination):
                try:
                    while data := await source.read(65536):
                        destination.write(data)
                        await destination.drain()
                finally:
                    destination.close()
            await asyncio.gather(pipe(reader, remote), pipe(upstream, writer), return_exceptions=True)
        except Exception as error:
            print(type(error).__name__, file=sys.stderr, flush=True)
            writer.close()
    server = await asyncio.start_server(handle, "127.0.0.1", 443)
    os.setgroups([])
    os.setgid(gid)
    os.setuid(uid)
    async with server:
        await server.serve_forever()


def connect():
    config = json.loads((PRIVATE / "remote.json").read_text())
    deadline = time.monotonic() + 900
    while True:
        try:
            with socket.create_connection((config["address"], 8443), timeout=10):
                break
        except OSError:
            if time.monotonic() >= deadline:
                raise RuntimeError("Runner-specific network access was not ready") from None
            time.sleep(5)
    (ROOT / ".build").mkdir(exist_ok=True)
    with (ROOT / ".build/private-relay.log").open("wb") as log:
        process = subprocess.Popen(["sudo", "-n", sys.executable, __file__, "serve", str(os.getuid()), str(os.getgid())],
                                   stdout=log, stderr=log, start_new_session=True)
    (PRIVATE / "relay.pid").write_text(str(process.pid))
    time.sleep(2)
    if process.poll() is not None:
        raise RuntimeError("Loopback relay failed")


if __name__ == "__main__":
    try:
        if os.environ.get("GITHUB_ACTIONS") != "true" and sys.argv[1] != "serve":
            raise RuntimeError("Disposable CI only")
        if sys.argv[1] == "prepare":
            prepare()
        elif sys.argv[1] == "connect":
            connect()
        elif sys.argv[1] == "serve":
            config = json.loads((PRIVATE / "remote.json").read_text())
            hosts = {urlsplit(config["probe"]["ISSUER_URL"]).hostname, config["probe"]["CALLBACK_HOST"]}
            if any(not host or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789.-" for c in host) for host in hosts):
                raise RuntimeError("Invalid hostname")
            with open("/etc/hosts", "a") as output:
                output.write("\n127.0.0.1 " + " ".join(sorted(hosts)) + "\n")
            asyncio.run(serve(config, int(sys.argv[2]), int(sys.argv[3])))
        else:
            raise RuntimeError("Unknown phase")
    except Exception:
        raise SystemExit("Remote probe transport failed; private configuration withheld.") from None
