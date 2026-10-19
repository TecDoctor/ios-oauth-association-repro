COMPOSE = docker compose -f compose.yml
.PHONY: docker.up docker.down caddy.download caddy.forward caddy.trust.iossim caddy.restart
docker.up:
	$(COMPOSE) up --build --detach --wait --wait-timeout 600
docker.down:
	$(COMPOSE) down --volumes
caddy.download:
	@test -n "$(CADDY_CERTIFICATE_PATH)"
	$(COMPOSE) cp caddy:/data/caddy/pki/authorities/local/root.crt "$(CADDY_CERTIFICATE_PATH)"
caddy.forward:
	ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -L 127.0.0.1:443:127.0.0.1:443 -L 127.0.0.1:1053:$(PROBE_VM_ADDRESS):1053 colima
caddy.trust.iossim:
	@test -n "$(SIMULATOR_UDID)" && test -f "$(CADDY_CERTIFICATE_PATH)"
	xcrun simctl keychain "$(SIMULATOR_UDID)" add-root-cert "$(CADDY_CERTIFICATE_PATH)"
caddy.restart:
	$(COMPOSE) restart caddy
