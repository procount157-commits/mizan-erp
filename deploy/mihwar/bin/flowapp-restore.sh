#!/usr/bin/env bash
# Restore a Flow Hub-family app's database from the dump shipped next to it,
# cleanly, and record every migration in the repo as applied — the dump comes
# from a database already migrated to this code (local copies never had the
# schema_migrations table, so deploy.sh would otherwise replay them all, and
# not all of them can run twice).
#   flowapp-restore.sh <dir>
set -euo pipefail
d=$1
cd /root/mihwar/$d
set -a; . ./.env; set +a
dump=$d.dump
[ -f "$dump" ] || { echo "no $dump"; exit 1; }

docker compose stop api web >/dev/null 2>&1 || true
docker compose up -d db
# A first start of Postgres restarts once after initdb: wait until it answers
# a real query twice, a second apart.
ok=0
for i in $(seq 1 60); do
  if docker compose exec -T db psql -U "$POSTGRES_USER" -d postgres -Atc "select 1" >/dev/null 2>&1; then
    ok=$((ok+1)); [ $ok -ge 2 ] && break
  else ok=0; fi
  sleep 1
done

docker compose exec -T db dropdb -U "$POSTGRES_USER" --if-exists --force "$POSTGRES_DB"
docker compose exec -T db createdb -U "$POSTGRES_USER" "$POSTGRES_DB"
docker compose exec -T db pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --role="$POSTGRES_USER" < "$dump" 2>&1 \
  | grep -vE "already exists" | tail -3 || true
echo "users: $(docker compose exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc 'select count(*) from users')"

PSQL="docker compose exec -T db psql -v ON_ERROR_STOP=1 -U $POSTGRES_USER -d $POSTGRES_DB"
$PSQL -qc "create table if not exists schema_migrations (name text primary key, applied_at timestamptz not null default now())"
for f in lib/db/migrations/[0-9][0-9][0-9]_*.sql; do
  $PSQL -qc "insert into schema_migrations (name) values ('$(basename "$f")') on conflict do nothing"
done
echo "migrations recorded: $($PSQL -Atc 'select count(*) from schema_migrations')"
touch .restored
