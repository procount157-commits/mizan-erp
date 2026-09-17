#!/usr/bin/env bash
# Back up every Odoo database and its filestore.
#
# An accounting system without backups is a liability, not an asset: the ledger
# is the client's legal record and losing it is not something a support call
# fixes. Both halves are needed — the database holds the entries, the filestore
# holds the attachments (signed invoices, receipts, uploaded bills), and a
# restore with only one of them is not a restore.
#
#   scripts/backup.sh                 # back up everything
#   scripts/backup.sh mizan           # back up one database
#
# Retention: daily backups are kept for KEEP_DAYS, then removed.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
dest="${BACKUP_DIR:-$root/backups}"
keep_days="${KEEP_DAYS:-30}"
stamp="$(date +%Y%m%d-%H%M%S)"

db_container="${DB_CONTAINER:-mizan-db}"
odoo_container="${ODOO_CONTAINER:-mizan-odoo}"
db_user="${POSTGRES_USER:-odoo}"

mkdir -p "$dest"

if ! docker ps --format '{{.Names}}' | grep -qx "$db_container"; then
    echo "Database container '$db_container' is not running." >&2
    exit 1
fi

databases=("$@")
if [ ${#databases[@]} -eq 0 ]; then
    mapfile -t databases < <(docker exec "$db_container" psql -U "$db_user" -d postgres -At \
        -c "SELECT datname FROM pg_database WHERE datistemplate = false AND datname <> 'postgres';")
fi

for db in "${databases[@]}"; do
    echo "backing up $db"
    out="$dest/${db}-${stamp}"

    # -Fc is the custom format: compressed, and restorable with pg_restore.
    docker exec "$db_container" pg_dump -U "$db_user" -Fc "$db" > "$out.dump"

    # The filestore lives inside the Odoo container, not the database.
    if docker ps --format '{{.Names}}' | grep -qx "$odoo_container"; then
        docker exec "$odoo_container" sh -c \
            "cd /var/lib/odoo/filestore && tar cf - '$db' 2>/dev/null" \
            > "$out-filestore.tar" || echo "  (no filestore for $db)"
    fi

    size=$(du -sh "$out.dump" | cut -f1)
    echo "  $out.dump ($size)"
done

# Prune old backups so the disk does not fill silently.
find "$dest" -name '*.dump' -mtime "+$keep_days" -delete
find "$dest" -name '*-filestore.tar' -mtime "+$keep_days" -delete

echo
echo "Done. Backups in $dest (kept $keep_days days)."
echo "Restore with: scripts/restore.sh <dump file> <target database>"
