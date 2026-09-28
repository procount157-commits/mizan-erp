# -*- coding: utf-8 -*-
"""Give employee advances an account of their own, and a ceiling.

Run once per database, and against the template so a new client gets it on day
one:

    docker exec -i mizan-odoo odoo shell -d <db> --no-http \
        --db_user odoo --db_password "$PW" < scripts/setup_advances.py

Three settings, and the reasoning for each.

AN ACCOUNT OF ITS OWN. An advance must sit in a current ASSET account while
the employee holds it, because the company is owed the money and has bought
nothing yet. The usual mistake is to post it to an expense account, which
recognises a cost that has not happened and — worse — takes the balance off
the balance sheet, so nobody is chasing it. It also must not share the
subcontractor advances account: those are recovered from claims, these from
expense reports, and mixing them makes both unreadable.

A JOURNAL. The advance is paid from somewhere real. Left unset, the module
refuses to post rather than choosing a bank account on the company's behalf.

A CEILING. Above it, an advance needs the override right, and the override is
recorded on the advance with the reason. 20,000 AED is a starting point a
finance manager should change, not a rule.
"""

company = env.company
print("company: %s" % company.name)

ADVANCE_CODE = "102600"
account = env["account.account"].search(
    [("code", "=", ADVANCE_CODE), ("company_ids", "in", company.id)], limit=1)
if not account:
    account = env["account.account"].search(
        [("code", "=", ADVANCE_CODE)], limit=1)
if not account:
    account = env["account.account"].create({
        "code": ADVANCE_CODE,
        "name": "سُلف الموظفين",
        "account_type": "asset_current",
        "reconcile": True,
    })
    print("created %s %s" % (account.code, account.name))
else:
    print("using  %s %s" % (account.code, account.name))

journal = (company.mizan_advance_journal_id
           or env["account.journal"].search(
               [("type", "=", "bank"), ("company_id", "=", company.id)],
               limit=1))
if not journal:
    print("WARNING: no bank journal. Advances cannot be paid until one exists.")

company.write({
    "mizan_advance_account_id": account.id,
    "mizan_advance_journal_id": journal.id if journal else False,
    # Change this. It is a placeholder, not a policy.
    "mizan_advance_limit": company.mizan_advance_limit or 20000.0,
})

print("account : %s" % company.mizan_advance_account_id.display_name)
print("journal : %s" % (company.mizan_advance_journal_id.display_name or "NOT SET"))
print("ceiling : %s %s" % (company.mizan_advance_limit,
                           company.currency_id.name))

outstanding = env["mizan.employee.advance"].search(
    [("state", "=", "paid"), ("amount_outstanding", ">", 0)])
if outstanding:
    print("\n%d advance(s) already outstanding, %0.2f in total:"
          % (len(outstanding), sum(outstanding.mapped("amount_outstanding"))))
    for advance in outstanding:
        print("  %-16s %-24s %12.2f" % (advance.name, advance.employee_id.name,
                                        advance.amount_outstanding))
else:
    print("\nNo advance is outstanding.")

env.cr.commit()
print("saved.")
