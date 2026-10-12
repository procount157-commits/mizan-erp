#!/usr/bin/env bash
# First start of a Flow Hub-family app on the shared Mihwar server.
#   flowapp-first-run.sh <dir> <host-port>
# Binds the app web server to 172.17.0.1:<port> (reached by the server Caddy,
# never by the internet), restores the database shipped next to it once, puts
# back its uploads, then runs the app own deploy/deploy.sh.
set -euo pipefail
d=$1 port=$2
cd /root/mihwar/$d
set -a; . ./.env; set +a
cat > docker-compose.override.yml <<YML
# Mihwar server: the door is the shared Caddy; this app listens on the host only.
services:
  web:
    ports: !override
      - "172.17.0.1:${port}:80"
  api:
    environment:
      SITE_URL: \${SITE_URL:-}
      ZHIPU_MODEL: \${ZHIPU_MODEL:-}
      OPEN_REGISTRATION: \${OPEN_REGISTRATION:-}
YML
docker compose up -d db
until docker compose exec -T db pg_isready -U "$POSTGRES_USER" >/dev/null 2>&1; do sleep 1; done
if [ ! -f .restored ]; then
  for f in $d.dump $d-schema.dump $d-users.dump; do
    [ -f "$f" ] || continue
    echo "restore $f"
    docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --role="$POSTGRES_USER" < "$f" 2>&1 | grep -vE "already exists|^pg_restore: (error: could not execute query|warning)" | tail -3 || true
  done
  touch .restored
fi
docker compose up -d --no-deps api 2>/dev/null || true
if [ -f $d-media.tgz ] && [ ! -f .media-restored ]; then
  docker compose run --rm --no-deps -T --entrypoint sh api -c "mkdir -p /data && tar -C /data -xzf -" < $d-media.tgz && touch .media-restored
fi
./deploy/deploy.sh
