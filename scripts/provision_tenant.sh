#!/usr/bin/env bash
# Build the golden template that every client database is copied from.
#
#   scripts/provision_tenant.sh --build-template
#
# Clients are NOT provisioned here. Provisioning happens in the operations
# console (Operations > Clients > Provision Client), which copies this template,
# regenerates the database uuid, clears the template's company identity and
# creates a support login — steps that are easy to do and easy to forget, and
# doing them in two places means doing one of them wrong.
#
# Copying beats installing: a full install takes about eight minutes and depends
# on whichever module versions are on disk that day, while a copy takes seconds
# and leaves every client byte-identical, so a bug found at one client
# reproduces at all of them.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
compose_dir="$root/docker"
db_container="${DB_CONTAINER:-mizan-db}"
db_user="${POSTGRES_USER:-odoo}"
db_password="${POSTGRES_PASSWORD:-}"
template="${TEMPLATE_DB:-mizan_template}"

if [ -z "$db_password" ] && [ -f "$compose_dir/.env" ]; then
    # shellcheck disable=SC1091
    set -a && . "$compose_dir/.env" && set +a
    db_user="${POSTGRES_USER:-odoo}"
    db_password="${POSTGRES_PASSWORD:-}"
fi

modules="mizan_core,mizan_contracting,mizan_cheque,mizan_documents,mizan_wps"

odoo_shell() {
    docker compose -f "$compose_dir/docker-compose.yml" exec -T odoo \
        odoo shell --config=/etc/odoo/odoo.conf \
        --db_user "$db_user" --db_password "$db_password" \
        -d "$template" --no-http
}

db_exists() {
    docker exec "$db_container" psql -U "$db_user" -d postgres -At \
        -c "SELECT 1 FROM pg_database WHERE datname = '$1';"
}

if [ "${1:-}" != "--build-template" ]; then
    cat >&2 <<'USAGE'
usage: scripts/provision_tenant.sh --build-template

Builds the golden template database. To create a client, open the operations
console and use Operations > Clients > Provision Client.
USAGE
    exit 1
fi

if [ -n "$(db_exists "$template")" ]; then
    echo "Template '$template' already exists. Drop it first to rebuild." >&2
    exit 1
fi

echo "Building template '$template' — installs every module once (~8 min)."
docker compose -f "$compose_dir/docker-compose.yml" run --rm --no-deps -T odoo odoo \
    --config=/etc/odoo/odoo.conf --db_user "$db_user" --db_password "$db_password" \
    -d "$template" --without-demo=all --stop-after-init -i "$modules"

echo "Loading the UAE chart of accounts."
odoo_shell <<'PY'
company = env.company
company.country_id = env.ref('base.ae').id
env['account.chart.template'].try_loading('ae', company, install_demo=False)
env.cr.commit()
PY

for script in arabize_coa build_account_groups add_contracting_accounts setup_uae_payroll; do
    echo "running $script"
    odoo_shell < "$root/scripts/$script.py" >/dev/null
done

# A template must carry no identity of its own: every client is copied from it,
# and anything left here — a tax number, a bank account, an address — is
# inherited by all of them.
echo "clearing template identity"
odoo_shell <<'PY'
company = env.company
company.write({
    'vat': False, 'company_registry': False,
    'street': False, 'street2': False, 'city': False, 'zip': False,
    'phone': False, 'email': False, 'website': False,
})
banks = env['res.partner.bank'].with_context(active_test=False).search(
    [('partner_id', '=', company.partner_id.id)])
banks.unlink()
left = banks.exists()
env.cr.commit()
print('bank accounts left on the template: %s' % (left.mapped('acc_number') or 'none'))
PY

cat <<EOF

Template ready: $template

Create clients from the operations console:
  Operations > Clients > Provision Client
EOF
