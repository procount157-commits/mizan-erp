#!/usr/bin/env bash
# Copy the OCA addons this deployment uses into the mizan_oca Docker volume.
#
# Why a volume and not a bind mount: Docker Desktop on macOS intermittently
# fails reads from bind mounts with EDEADLK ("Resource deadlock avoided"), which
# makes Odoo silently skip modules. `docker cp` reads the files natively on the
# host instead, so the copy is reliable. On a Linux server a plain bind mount
# works and this script is unnecessary.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
src="$root/third_party/OCA"
volume=mizan_oca
helper=oca_seed

# Addons actually installed in the Mizan deployment, as <repo>/<module>.
modules=(
    server-ux/date_range
    server-ux/base_revision
    server-ux/base_tier_validation
    server-ux/base_tier_validation_formula
    reporting-engine/report_xlsx
    reporting-engine/report_xlsx_helper
    account-financial-reporting/account_financial_report
    # Balance sheet and profit & loss. Community ships neither, and
    # account_financial_report stops at ledgers and the trial balance.
    mis-builder/mis_builder
    mis-builder/mis_builder_budget
    account-financial-reporting/account_tax_balance
    account-financial-reporting/partner_statement
    account-financial-tools/account_asset_management
    account-closing/account_fiscal_year_closing
    account-reconcile/account_reconcile_oca
    # Importing the bank's own file is what makes reconciliation automatic.
    # Formats first, then the bridge that feeds them into the reconcile widget.
    bank-statement-import/account_statement_import_base
    bank-statement-import/account_statement_import_file
    bank-statement-import/account_statement_import_camt
    bank-statement-import/account_statement_import_sheet_file
    bank-statement-import/account_statement_import_file_reconcile_oca
    account-reconcile/account_statement_base
    account-reconcile/account_reconcile_model_oca
    account-budgeting/account_budget_oca
    project/project_budget
    project/project_milestone_status
    project/project_role
    purchase-workflow/purchase_request
    purchase-workflow/purchase_request_tier_validation
    purchase-workflow/purchase_request_department
    sale-workflow/sale_order_revision
    contract/contract
    stock-logistics-barcode/barcodes_generator_abstract
    stock-logistics-barcode/barcodes_generator_product
    stock-logistics-barcode/product_multi_barcode
    stock-logistics-barcode/stock_picking_product_barcode_report
    stock-logistics-barcode/web_ir_actions_client_scan
)

docker volume create "$volume" >/dev/null
docker rm -f "$helper" >/dev/null 2>&1 || true
docker create --name "$helper" -v "$volume":/oca alpine true >/dev/null

ok=0
for m in "${modules[@]}"; do
    if [ ! -d "$src/$m" ]; then
        echo "MISSING $m — run scripts/fetch-oca.sh first" >&2
        continue
    fi
    docker cp "$src/$m" "$helper:/oca/" >/dev/null
    ok=$((ok + 1))
done

docker rm -f "$helper" >/dev/null
echo "copied $ok/${#modules[@]} addons into volume '$volume'"
