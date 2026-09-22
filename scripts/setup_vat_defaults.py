# -*- coding: utf-8 -*-
"""Make 5% VAT arrive by itself on every line.

The taxes were all defined and the company defaults were set, yet a line typed
by hand came out with NO tax at all. That is not a missing tax — it is a
misunderstanding of where Odoo looks.

`account_sale_tax_id` on the company does not reach an invoice line. It is the
default for NEW PRODUCTS. A line gets its tax from the product, or, when there
is no product, from the ACCOUNT it posts to. A contractor bills work, not
products, so almost every line is typed straight onto an account — and every
one of them was coming out with no VAT until somebody remembered to add it.

Understating output VAT is not a tidy-up. So the tax goes on the accounts:
income accounts carry the sale tax, expense accounts the purchase tax, and the
line picks it up whatever the accountant types.

The emirate matters too. The UAE return reports sales BY EMIRATE, and the
company default here was Abu Dhabi for a Dubai company. It is set from where
the company actually is — and for contracting the right emirate is where the
work is, so a claim takes it from its contract instead (see mizan_contracting).
"""

from odoo.exceptions import UserError

company = env.company
Tax = env["account.tax"]
Account = env["account.account"]

EMIRATE_CODES = {
    "dubai": "DB", "دبي": "DB",
    "abu dhabi": "AD", "أبوظبي": "AD", "ابوظبي": "AD", "أبو ظبي": "AD",
    "sharjah": "S", "الشارقة": "S",
    "ajman": "A", "عجمان": "A",
    "umm al quwain": "UAQ", "أم القيوين": "UAQ",
    "ras al khaimah": "RAK", "رأس الخيمة": "RAK",
    "fujairah": "F", "الفجيرة": "F",
}


def emirate_suffix():
    city = (company.partner_id.city or "").strip().lower()
    state = (company.partner_id.state_id.name or "").strip().lower()
    for key, code in EMIRATE_CODES.items():
        if key in city or key in state:
            return code
    return None


suffix = emirate_suffix()
sale_tax = None
if suffix:
    sale_tax = Tax.search([
        ("type_tax_use", "=", "sale"), ("amount", "=", 5.0),
        ("company_id", "=", company.id), ("name", "=like", "5%% %s" % suffix),
    ], limit=1)
if not sale_tax:
    # No emirate recognised: take the plain 5% sale tax rather than whichever
    # emirate happens to sort first, which is how Abu Dhabi ended up as the
    # default for a Dubai company.
    sale_tax = Tax.search([
        ("type_tax_use", "=", "sale"), ("amount", "=", 5.0),
        ("company_id", "=", company.id), ("name", "in", ("5%", "5% DB")),
    ], limit=1)
purchase_tax = Tax.search([
    ("type_tax_use", "=", "purchase"), ("amount", "=", 5.0),
    ("company_id", "=", company.id), ("name", "=", "5%"),
], limit=1)

if not (sale_tax and purchase_tax):
    raise UserError("The 5%% UAE taxes are missing. Install l10n_ae first.")

company.write({
    "account_sale_tax_id": sale_tax.id,
    "account_purchase_tax_id": purchase_tax.id,
})

# --------------------------------------------------- the tax on the accounts
SALE_TYPES = ("income", "income_other")
PURCHASE_TYPES = ("expense", "expense_direct_cost", "expense_depreciation")

# Accounts that must NEVER carry a tax, whatever their type. Progress billings
# is a liability, but the deeper point is that a claim's VAT is decided by the
# claim, and revenue recognition is an internal entry with no VAT at all —
# putting a tax on 501001 would attach output VAT to a journal entry nobody
# ever invoiced.
NEVER = {"501001", "204004", "204005", "107002", "401011"}

touched = {"sale": 0, "purchase": 0, "skipped": 0}
for account in Account.search([("company_ids", "in", company.id)]):
    code = account.code or ""
    if code in NEVER:
        touched["skipped"] += 1
        continue
    if account.tax_ids:
        continue
    if account.account_type in SALE_TYPES:
        account.tax_ids = [(6, 0, sale_tax.ids)]
        touched["sale"] += 1
    elif account.account_type in PURCHASE_TYPES:
        account.tax_ids = [(6, 0, purchase_tax.ids)]
        touched["purchase"] += 1

env.cr.commit()

print()
print("company emirate detected : %s" % (suffix or "none — used the plain 5%"))
print("default sale tax         : %s" % sale_tax.with_context(lang="en_US").name)
print("default purchase tax     : %s" % purchase_tax.with_context(lang="en_US").name)
print("income accounts tagged   : %d" % touched["sale"])
print("expense accounts tagged  : %d" % touched["purchase"])
print("deliberately left clean  : %d" % touched["skipped"])
print()

# ------------------------------------------------------------- the proof
for move_type, code, label in (
        ("out_invoice", "500001", "customer invoice"),
        ("in_invoice", "401001", "vendor bill")):
    account = Account.search([("code", "=", code)], limit=1)
    if not account:
        account = Account.search([
            ("account_type", "in",
             SALE_TYPES if move_type == "out_invoice" else PURCHASE_TYPES),
            ("code", "not in", list(NEVER))], limit=1)
    move = env["account.move"].new({"move_type": move_type})
    line = env["account.move.line"].new({
        "move_id": move.id, "name": "test",
        "account_id": account.id, "price_unit": 1000.0,
    })
    print("%-18s on %s -> %s" % (
        label, account.code,
        ", ".join(line.tax_ids.mapped("name")) or "STILL NONE"))
