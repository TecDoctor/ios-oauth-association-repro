#!/bin/bash
set -euo pipefail
[[ ${GITHUB_ACTIONS:-} == true && ${RUNNER_ENVIRONMENT:-} == github-hosted ]]
[[ $(uname -s) == Darwin && $(uname -m) == x86_64 ]]
root="$RUNNER_TEMP/docker-tools"
mkdir -p "$root/bin" "$HOME/.docker/cli-plugins"
cd "$root"
fetch() {
  curl --fail --location --silent --show-error --max-time 180 "$1" -o "$2"
  echo "$3  $2" | shasum -a 256 -c -
}
fetch https://github.com/lima-vm/lima/releases/download/v1.2.1/lima-1.2.1-Darwin-x86_64.tar.gz lima.tgz f6ba629f70fe245e74dbba670bfaf88aaa58f5785d9365ce826d6662449a02e7
fetch https://github.com/abiosoft/colima/releases/download/v0.9.1/colima-Darwin-x86_64 bin/colima d90efd431713d4db57a2083fbf4154c57c63d7e5a2292170c8eaa89fb2e3efed
fetch https://download.docker.com/mac/static/stable/x86_64/docker-28.3.3.tgz docker.tgz e1d2a1a46ecdb4942bc12e1a6759bca3f2b2f1cfc1a5f3f921719b4d52fd3076
fetch https://github.com/docker/compose/releases/download/v2.39.4/docker-compose-darwin-x86_64 "$HOME/.docker/cli-plugins/docker-compose" ec56a48c47ff30db7626f980f36e48d9573114626c2beb6b76b47dd6ff4aa63c
tar -xzf lima.tgz
tar -xzf docker.tgz
ln -s "$root/docker/docker" bin/docker
chmod +x bin/colima "$HOME/.docker/cli-plugins/docker-compose"
export PATH="$root/bin:$PATH"
echo "$root/bin" >> "$GITHUB_PATH"
colima start --cpu 2 --memory 6 --disk 40 --arch x86_64 --vm-type vz --mount-type virtiofs
docker info
docker compose version
