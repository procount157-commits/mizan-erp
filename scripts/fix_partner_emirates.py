# -*- coding: utf-8 -*-
"""Give existing UAE partners their emirate, and report the ones nobody can.

Run once per database after the emirate logic is installed. It reports rather
than guesses, and it separates the two cases because they are not equally
serious:

  * a CUSTOMER with no emirate is a VAT RETURN problem. Form 201 reports sales
    by emirate, so the revenue lands in the wrong box — or, while the emirate
    is empty, gets zero-rated by the Non-UAE catch-all and is not reported at
    all.
  * a VENDOR with no emirate only affects whether the purchase is treated as
    domestic or as reverse charge. Purchases are not reported by emirate, so
    for a partner already marked as being in the UAE the company's own emirate
    is a safe fill: it produces the correct domestic 5%, which is the thing
    that actually matters.
"""

Partner = env["res.partner"]
company = env.company

company.partner_id._mizan_apply_emirate()
if not company.partner_id.state_id:
    print("WARNING: the company itself has no emirate. Set its city first.")

partners = Partner.search([
    ("country_id.code", "=", "AE"),
    "|", ("customer_rank", ">", 0), ("supplier_rank", ">", 0),
])
partners._mizan_apply_emirate()

resolved, customers_blocked, vendors_filled = [], [], []
for partner in partners:
    if partner.state_id:
        resolved.append(partner)
        continue
    if partner.customer_rank > 0:
        customers_blocked.append(partner)
    elif company.partner_id.state_id:
        partner.state_id = company.partner_id.state_id.id
        vendors_filled.append(partner)

env.cr.commit()

FP = env["account.fiscal.position"]
sale_tax = company.account_sale_tax_id

print()
print("company emirate : %s" % (company.partner_id.state_id.name or "NOT SET"))
print()
print("%-40s %-12s %-16s %s" % ("partner", "emirate", "position", "5% becomes"))
print("-" * 92)
for partner in partners:
    fp = FP._get_fiscal_position(partner)
    mapped = fp.map_tax(sale_tax) if fp else sale_tax
    print("%-40s %-12s %-16s %s" % (
        partner.display_name[:40],
        partner.state_id.code or "NONE",
        (fp.with_context(lang="en_US").name if fp else "none")[:16],
        ", ".join(mapped.mapped("name")) or "REMOVED"))

print()
print("resolved from the city or the company : %d" % (
    len(resolved) + len(vendors_filled)))
if vendors_filled:
    print("vendors filled with the company's emirate (purchases are not")
    print("reported by emirate, so this only makes them domestic 5%%):")
    for partner in vendors_filled:
        print("   %s" % partner.display_name)
if customers_blocked:
    print()
    print("CUSTOMERS STILL WITHOUT AN EMIRATE — set these by hand, they decide")
    print("which box of the VAT return their revenue is reported in:")
    for partner in customers_blocked:
        print("   %s" % partner.display_name)
else:
    print("every customer has an emirate.")
