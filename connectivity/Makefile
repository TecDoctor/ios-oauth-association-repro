.PHONY: docker.up docker.down
docker.up:
	docker compose -f compose.yml up -d --wait --wait-timeout 120
docker.down:
	docker compose -f compose.yml down
