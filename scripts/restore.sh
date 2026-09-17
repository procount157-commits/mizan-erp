#!/usr/bin/env bash
# Restore a database and its filestore from scripts/backup.sh output.
#
#   scripts/restore.sh backups/mizan-20260917-120000.dump mizan_restored
#
# A backup nobody has restored is a guess, not a backup — restore into a scratch
# database and open it before you ever need this in anger.
set -euo pipefail

dump="${1:-}"
target="${2:-}"

if [ -z "$dump" ] || [ -z "$target" ]; then
    echo "usage: scripts/restore.sh <dump file> <target database>" >&2
    exit 1
fi
if [ ! -f "$dump" ]; then
    echo "No such dump: $dump" >&2
    exit 1
fi

db_container="${DB_CONTAINER:-mizan-db}"
odoo_container="${ODOO_CONTAINER:-mizan-odoo}"
db_user="${POSTGRES_USER:-odoo}"

exists=$(docker exec "$db_container" psql -U "$db_user" -d postgres -At \
    -c "SELECT 1 FROM pg_database WHERE datname = '$target';")
if [ -n "$exists" ]; then
    echo "Database '$target' already exists. Drop it first, or pick another name." >&2
    exit 1
fi

echo "creating $target"
docker exec "$db_container" createdb -U "$db_user" "$target"

echo "restoring data"
docker exec -i "$db_container" pg_restore -U "$db_user" -d "$target" --no-owner < "$dump"

# Restore the filestore alongside, if the matching tar is there.
fs="${dump%.dump}-filestore.tar"
if [ -f "$fs" ]; then
    source_db=$(basename "$dump" | sed 's/-[0-9]\{8\}-[0-9]\{6\}\.dump$//')
    echo "restoring filestore"
    docker exec "$odoo_container" mkdir -p /var/lib/odoo/filestore
    docker exec -i "$odoo_container" tar xf - -C /var/lib/odoo/filestore < "$fs"
    if [ "$source_db" != "$target" ]; then
        docker exec "$odoo_container" sh -c \
            "cd /var/lib/odoo/filestore && rm -rf '$target' && mv '$source_db' '$target'"
    fi
    docker exec -u root "$odoo_container" chown -R odoo:odoo /var/lib/odoo/filestore
fi

cat <<EOF

Restored into '$target'.

A restored copy still points at the original's outgoing mail and scheduled
actions. Before opening it as anything other than a read-only check, neutralise
it so it cannot email real clients:

  docker compose exec odoo odoo neutralize --config=/etc/odoo/odoo.conf -d $target
EOF
