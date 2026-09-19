#!/usr/bin/env bash
# Point every client database at one outgoing mail server.
#
#   SMTP_HOST=smtp-relay.brevo.com SMTP_PORT=587 \
#   SMTP_USER=xxxxx SMTP_PASS=yyyyy SMTP_FROM=invoices@proaccount.ae \
#   scripts/configure_mail.sh
#
# One relay for every tenant, not one per client. A shared authenticated relay
# is what keeps deliverability manageable: the sending domain, its SPF, DKIM and
# DMARC records and its reputation are yours, and a new client inherits a warm
# domain instead of starting from an unknown one that lands in spam.
#
# The client's own address still appears to the recipient, because the template
# sends as the company and the relay only carries it.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_dir="$root/docker"
db_container="${DB_CONTAINER:-mizan-db}"

if [ -f "$compose_dir/.env" ]; then
    set -a && . "$compose_dir/.env" && set +a
fi
db_user="${POSTGRES_USER:-odoo}"
db_password="${POSTGRES_PASSWORD:-}"

: "${SMTP_HOST:?set SMTP_HOST}"
: "${SMTP_USER:?set SMTP_USER}"
: "${SMTP_PASS:?set SMTP_PASS}"
smtp_port="${SMTP_PORT:-587}"
smtp_from="${SMTP_FROM:-}"
encryption="${SMTP_ENCRYPTION:-starttls}"

databases=$(docker exec "$db_container" psql -U "$db_user" -d postgres -At -c "
    SELECT datname FROM pg_database
     WHERE datistemplate = false AND datname NOT IN ('postgres');")

for db in $databases; do
    # Only databases that are actually Odoo clients.
    has_odoo=$(docker exec "$db_container" psql -U "$db_user" -d "$db" -At -c "
        SELECT 1 FROM information_schema.tables
         WHERE table_name = 'ir_mail_server' LIMIT 1;" 2>/dev/null || true)
    [ -n "$has_odoo" ] || continue

    echo "configuring mail for $db"
    docker compose -f "$compose_dir/docker-compose.yml" exec -T odoo \
        odoo shell --config=/etc/odoo/odoo.conf \
        --db_user "$db_user" --db_password "$db_password" \
        -d "$db" --no-http <<PY 2>/dev/null | grep -E '^mail:' || true
server = env['ir.mail_server'].search([('name', '=', 'ProAccount Relay')], limit=1)
values = {
    'name': 'ProAccount Relay',
    'smtp_host': '$SMTP_HOST',
    'smtp_port': $smtp_port,
    'smtp_user': '$SMTP_USER',
    'smtp_pass': '$SMTP_PASS',
    'smtp_encryption': '$encryption',
    'sequence': 5,
}
if server:
    server.write(values)
else:
    server = env['ir.mail_server'].create(values)
params = env['ir.config_parameter'].sudo()
if '$smtp_from':
    params.set_param('mail.default.from', '$smtp_from'.split('@')[0])
    params.set_param('mail.catchall.domain', '$smtp_from'.split('@')[-1])
params.set_param('mail.bounce.alias', 'bounce')
env.cr.commit()
print('mail: %s via %s:%s' % (server.name, server.smtp_host, server.smtp_port))
PY
done

cat <<'DONE'

Done. Test from inside a client:
  Settings > Technical > Email > Outgoing Mail Servers > Test Connection

If mail lands in spam, the cause is almost always DNS rather than Odoo: the
sending domain needs SPF authorising the relay, a DKIM key published by it, and
a DMARC record. Deliverability is a property of the domain, not the software.
DONE
