# -*- coding: utf-8 -*-
"""Bank fees reconcile themselves.

Every statement carries the same few lines nobody raises a document for: the
monthly fee, transfer charges, and the VAT on them. A rule per kind books them
the moment the statement is imported. The VAT goes to input VAT, not to fees —
it is recoverable, and booking it as a cost overstates expenses and loses the
credit on the return."""

FEE_PATTERN = r"(?i).*(\bCHG\b|CHARGES?\b|SERVICE FEE|ACCOUNT FEE|COMMISSION|TT FEE|رسوم|عمولة)"
VAT_PATTERN = r"(?i).*(VAT|ضريبة).*(CHARGE|FEE|COMMISSION|رسوم|عمولة)"


def _account(env, codes, name_like):
    Account = env["account.account"].with_company(env.company)
    for code in codes:
        account = Account.search([("code", "=", code)], limit=1)
        if account:
            return account
    return Account.search([("name", "ilike", name_like)], limit=1)


def setup_bank_fee_rules(env):
    Model = env["account.reconcile.model"]
    fees = _account(env, ["400051", "6261"], "Bank Charges")
    tax = env.company.account_purchase_tax_id
    input_vat = tax.invoice_repartition_line_ids.filtered(lambda l: l.repartition_type == "tax").account_id[:1] \
        if tax else env["account.account"]
    if not fees:
        return
    vat_rule = Model.search([("name", "=", "Bank charges — VAT")], limit=1)
    vat_values = {"match_label_param": VAT_PATTERN}
    if vat_rule:
        vat_rule.write(vat_values)
    elif input_vat:
        Model.create({
            "name": "Bank charges — VAT", "rule_type": "writeoff_suggestion", "sequence": 5,
            "match_nature": "amount_paid", "match_label": "match_regex", "match_label_param": VAT_PATTERN,
            "auto_reconcile": True,
            "line_ids": [(0, 0, {"account_id": input_vat.id, "amount_type": "percentage",
                                 "amount_string": "100", "label": "VAT on bank charges"})],
        })
    fee_rule = Model.search([("name", "=", "Bank Charges")], limit=1)
    values = {"match_label": "match_regex", "match_label_param": FEE_PATTERN,
              "match_nature": "amount_paid", "auto_reconcile": True, "sequence": 6}
    if fee_rule:
        fee_rule.write(values)
    else:
        Model.create(dict(values, name="Bank Charges", rule_type="writeoff_suggestion",
                          line_ids=[(0, 0, {"account_id": fees.id, "amount_type": "percentage",
                                            "amount_string": "100", "label": "Bank charges"})]))


def post_init_hook(env):
    for company in env["res.company"].search([]):
        setup_bank_fee_rules(env(context=dict(env.context, allowed_company_ids=[company.id])))
