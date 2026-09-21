# -*- coding: utf-8 -*-
"""Bills of quantities for الأمانة's two contracts, and claims measured from them.

Two jobs to do here, and they are different in kind.

The first is history. Both contracts were already billed with lump-sum claims —
a figure and a date. Those invoices are posted and numbered and cannot be
rewritten, so the measured sheets for them are reconstructed: the same total,
distributed across the priced items by where the job actually was at that date.
They are written straight into the certified state and pointed at the invoice
that already exists, because creating a second invoice for work already billed
is the one mistake that matters here. The reconstruction is scaled so each
sheet's cumulative value lands exactly on what was invoiced — otherwise
"previously certified" on the next claim disagrees with the ledger, and the
whole point of the bill is that those two numbers are the same number.

The second is the real thing: claim 3 on each contract, measured item by item
with no target to hit, taken all the way through submission, certification, the
tax invoice, the retention withheld and the advance recovered.
"""
from datetime import date

from odoo.exceptions import UserError

Contract = env["mizan.contract"]
Boq = env["mizan.contract.boq.line"]
Claim = env["mizan.progress.claim"]
Code = env["mizan.cost.code"]
Move = env["account.move"]

villa = Contract.search([("code", "=", "CT-2026-001")], limit=1)
school = Contract.search([("code", "=", "CT-2026-002")], limit=1)
if not (villa and school):
    raise UserError("Both contracts must exist. Run the client seed first.")
if villa.boq_line_ids or school.boq_line_ids:
    raise UserError(
        "A bill of quantities already exists on one of these contracts.\n"
        "Re-running would duplicate the priced items and the claims measured\n"
        "from them. Delete the existing bill first if that is what you want.")


def code(ref):
    record = Code.search([("code", "=", ref)], limit=1)
    if not record:
        raise UserError("Cost code %s is missing. Run scripts/setup_cost_codes.py." % ref)
    return record.id


# ============================================================== the priced bills
# (section, item no, description, unit, qty, rate, cost code)
# The last item of each bill carries no rate: it absorbs the difference between
# the priced items and the signed contract value, which is what an "external
# works" or "sundries" item does on a real bill.
VILLA = [
    ("تمهيدية", "01.01", "تجهيز الموقع والتسوير والخدمات المؤقتة", "LS", 1, 60000, "01-100"),
    ("تمهيدية", "01.02", "الإدارة والإشراف بالموقع", "month", 12, 7500, "01-200"),
    ("أعمال الأساسات", "02.01", "الحفر حتى المناسيب المطلوبة", "m3", 1800, 45, "02-100"),
    ("أعمال الأساسات", "02.02", "الردم والرص", "m3", 900, 30, "02-100"),
    ("أعمال الأساسات", "03.01", "خرسانة النظافة والأساسات", "m3", 320, 420, "03-100"),
    ("أعمال الأساسات", "03.03", "حديد تسليح — الأساسات", "ton", 48, 3200, "03-300"),
    ("الهيكل الخرساني", "03.02", "خرسانة الأعمدة والأسقف", "m3", 480, 430, "03-200"),
    ("الهيكل الخرساني", "03.04", "حديد تسليح — الهيكل", "ton", 66, 3200, "03-300"),
    ("الهيكل الخرساني", "03.05", "الشدة والسقالات", "m2", 3300, 55, "03-400"),
    ("الهيكل الخرساني", "04.01", "أعمال البلوك الخارجي والداخلي", "m2", 2400, 78, "04-100"),
    ("التشطيبات", "07.01", "العزل المائي — الأسطح والمناطق الرطبة", "m2", 620, 85, "07-100"),
    ("التشطيبات", "09.01", "اللياسة الداخلية والخارجية", "m2", 4200, 33, "09-100"),
    ("التشطيبات", "09.02", "بلاط الأرضيات والحوائط", "m2", 1150, 120, "09-200"),
    ("التشطيبات", "09.03", "الدهانات الداخلية والخارجية", "m2", 4200, 24, "09-300"),
    ("التشطيبات", "08.01", "الأبواب والنوافذ والزجاج", "LS", 1, 126000, "08-100"),
    ("الأعمال الكهروميكانيكية", "15.01", "السباكة والصرف", "LS", 1, 118000, "15-100"),
    ("الأعمال الكهروميكانيكية", "15.02", "التكييف والتهوية", "LS", 1, 155000, "15-200"),
    ("الأعمال الكهروميكانيكية", "16.01", "الأعمال الكهربائية", "LS", 1, 148000, "16-100"),
    ("الأعمال الخارجية", "40.01", "الأعمال الخارجية وسور الحدود والتنسيق", "LS", 1, None, "01-300"),
]

SCHOOL = [
    ("تمهيدية", "01.01", "تجهيز الموقع والأعمال المؤقتة", "LS", 1, 140000, "01-100"),
    ("تمهيدية", "01.02", "الإدارة والإشراف بالموقع", "month", 14, 12000, "01-200"),
    ("أعمال الأساسات", "02.01", "الحفر والأعمال الترابية", "m3", 4200, 36, "02-100"),
    ("أعمال الأساسات", "02.02", "التدعيم ونزح المياه", "LS", 1, 95000, "02-200"),
    ("أعمال الأساسات", "03.01", "خرسانة الأساسات", "m3", 640, 410, "03-100"),
    ("أعمال الأساسات", "03.03", "حديد تسليح — الأساسات", "ton", 82, 3150, "03-300"),
    ("الهيكل الخرساني", "03.02", "خرسانة الهيكل والأسقف", "m3", 980, 425, "03-200"),
    ("الهيكل الخرساني", "03.04", "حديد تسليح — الهيكل", "ton", 140, 3150, "03-300"),
    ("الهيكل الخرساني", "03.05", "الشدة والسقالات", "m2", 8600, 44, "03-400"),
    ("الهيكل الخرساني", "05.01", "الإنشاءات المعدنية — سقف القاعة", "ton", 36, 6800, "05-100"),
    ("الهيكل الخرساني", "04.01", "أعمال البلوك", "m2", 6200, 62, "04-100"),
    ("التشطيبات", "07.01", "العزل المائي والحراري", "m2", 2400, 68, "07-100"),
    ("التشطيبات", "09.01", "اللياسة والتجليط", "m2", 11500, 25, "09-100"),
    ("التشطيبات", "09.02", "البلاط والأرضيات", "m2", 3800, 88, "09-200"),
    ("التشطيبات", "09.03", "الدهانات", "m2", 11500, 17, "09-300"),
    ("التشطيبات", "08.01", "الأبواب والنوافذ والألمنيوم", "LS", 1, 280000, "08-100"),
    ("الأعمال الكهروميكانيكية", "15.01", "السباكة والصرف", "LS", 1, 240000, "15-100"),
    ("الأعمال الكهروميكانيكية", "15.02", "التكييف والتهوية", "LS", 1, 360000, "15-200"),
    ("الأعمال الكهروميكانيكية", "15.03", "مكافحة الحريق والإنذار", "LS", 1, 175000, "15-300"),
    ("الأعمال الكهروميكانيكية", "16.01", "الأعمال الكهربائية", "LS", 1, 330000, "16-100"),
    ("الأعمال الكهروميكانيكية", "16.02", "التيار الخفيف والبيانات", "LS", 1, 120000, "16-200"),
    ("الأعمال الخارجية", "40.01", "الأعمال الخارجية والملاعب والتنسيق", "LS", 1, None, "01-300"),
]


def build_bill(contract, rows):
    """Price the bill, letting the last item absorb the balance."""
    priced = sum(qty * rate for *_, qty, rate, _c in rows if rate is not None)
    balance = contract.contract_value - priced
    if balance <= 0:
        raise UserError(
            "%s: the priced items already exceed the contract value by %s."
            % (contract.code, -balance))
    created = Boq.browse()
    for index, (section, item_no, name, unit, qty, rate, cost_code) in enumerate(rows):
        created |= Boq.with_context(lang="en_US").create({
            "contract_id": contract.id,
            "sequence": (index + 1) * 10,
            "section": section,
            "item_no": item_no,
            "name": name,
            "unit": unit,
            "quantity": qty,
            "rate": rate if rate is not None else balance / qty,
            "cost_code_id": code(cost_code),
        })
    return created


villa_bill = build_bill(villa, VILLA)
school_bill = build_bill(school, SCHOOL)

# ====================================================== reconstructed history
# Cumulative percentage per item at each historical claim date. Scaled as a
# whole so the sheet's total lands on what was invoiced.
VILLA_STAGES = {
    1: {"01.01": 100, "01.02": 25, "02.01": 100, "02.02": 60, "03.01": 100,
        "03.03": 85, "03.02": 20, "03.04": 15, "03.05": 25},
    2: {"01.01": 100, "01.02": 50, "02.01": 100, "02.02": 100, "03.01": 100,
        "03.03": 100, "03.02": 75, "03.04": 70, "03.05": 70, "04.01": 40,
        "07.01": 25},
}
SCHOOL_STAGES = {
    1: {"01.01": 100, "01.02": 21, "02.01": 100, "02.02": 100, "03.01": 65,
        "03.03": 55, "03.05": 10},
    2: {"01.01": 100, "01.02": 43, "02.01": 100, "02.02": 100, "03.01": 100,
        "03.03": 100, "03.02": 35, "03.04": 30, "03.05": 35, "05.01": 15},
}
INVOICES = {
    ("CT-2026-001", 1): ("ALAMANA-YTD-2026 CLAIM-V1", date(2026, 3, 31), date(2026, 1, 1)),
    ("CT-2026-001", 2): ("ALAMANA-YTD-2026 CLAIM-V2", date(2026, 6, 30), date(2026, 4, 1)),
    ("CT-2026-002", 1): ("ALAMANA-YTD-2026 CLAIM-S1", date(2026, 5, 31), date(2026, 2, 1)),
    ("CT-2026-002", 2): ("ALAMANA-YTD-2026 CLAIM-S2", date(2026, 8, 31), date(2026, 6, 1)),
}
CONSULTANT = {"CT-2026-001": "م. سامي خليل — الاستشاري",
              "CT-2026-002": "دار الهندسة — الاستشاري المعتمد"}

def fit_stage(by_item, raw, target, contract_code, number):
    """Measure the staged items up or down until the sheet totals the target.

    Items that reach 100% stop moving and the rest take up the difference,
    which is how a sheet behaves: you cannot measure more concrete than the
    bill contains, so the balance has to appear in the trades still running.
    """
    pct = dict(raw)
    for _ in range(50):
        gross = sum(by_item[i].amount * p / 100.0 for i, p in pct.items())
        if abs(gross - target) < 0.5:
            return pct
        movable = [i for i in pct if pct[i] < 100.0 - 1e-9]
        movable_value = sum(by_item[i].amount * pct[i] / 100.0 for i in movable)
        if movable_value <= 0:
            break
        factor = (target - (gross - movable_value)) / movable_value
        if factor <= 0:
            break
        for i in movable:
            pct[i] = min(pct[i] * factor, 100.0)
    raise UserError(
        "%s claim %s: the staged items cannot reach %s even measured in full. "
        "Add the trades that were actually running at that date."
        % (contract_code, number, target))


report = []


def reconstruct(contract, bill, stages):
    for number in sorted(stages):
        ref, claim_date, period_start = INVOICES[(contract.code, number)]
        invoice = Move.search([("ref", "=", ref), ("state", "=", "posted")], limit=1)
        if not invoice:
            raise UserError("Invoice %s not found." % ref)
        # The target is the CUMULATIVE value the sheet has to state, so every
        # invoice raised on this contract up to and including this one. A claim
        # states the job from the start each time; matching it to one invoice's
        # amount would restate the job as only this period's work.
        target = 0.0
        for earlier in range(1, number + 1):
            earlier_ref = INVOICES[(contract.code, earlier)][0]
            earlier_invoice = Move.search(
                [("ref", "=", earlier_ref), ("state", "=", "posted")], limit=1)
            if not earlier_invoice:
                raise UserError("Invoice %s not found." % earlier_ref)
            target += earlier_invoice.amount_untaxed

        # What was measured at the two earlier dates, item by item, fitted to
        # the invoiced total. Fitted rather than scaled by one factor: an item
        # already at 100% cannot be measured further, so a single factor loses
        # exactly the amount it clips off the finished items and leaves the
        # sheet short — the first attempt at this pushed backfill 278 m3 past
        # the bill quantity trying to make up the difference.
        by_item = {line.item_no: line for line in bill}
        fitted = fit_stage(by_item, stages[number], target, contract.code, number)

        claim = Claim.create({
            "contract_id": contract.id,
            "sequence_no": number,
            "date": claim_date,
            "period_start": period_start,
            "period_end": claim_date,
            "retention_percent": contract.retention_percent,
        })
        lines = []
        for line in bill:
            pct = fitted.get(line.item_no, 0.0)
            cumulative_qty = round(line.quantity * pct / 100.0, 3)
            previous = 0.0
            if number > 1:
                earlier = env["mizan.progress.claim.line"].search([
                    ("boq_line_id", "=", line.id),
                    ("claim_id.contract_id", "=", contract.id),
                    ("claim_id.sequence_no", "<", number),
                ])
                previous = sum(earlier.mapped("this_qty"))
            lines.append((0, 0, {
                "boq_line_id": line.id,
                "this_qty": cumulative_qty - previous,
            }))
        claim.write({"line_ids": lines})

        # Most of the difference is absorbed on the finest-rated item measured,
        # which is what a quantity surveyor does. What is left is the rounding
        # of a quantity: a bill measured in cubic metres cannot land exactly on
        # a lump sum that was never measured. The residue is reported rather
        # than buried, and it is fils on six figures.
        drift = target - claim.gross_to_date
        if abs(drift) > 0.005:
            # Only an item with quantity still unmeasured can absorb it;
            # loading it onto a finished item is over-measurement.
            headroom = claim.line_ids.filtered(
                lambda l: l.this_qty and l.rate
                and (l.quantity - l.cumulative_qty) * l.rate > abs(drift))
            absorber = headroom.sorted(key=lambda l: l.rate)[:1]
            if not absorber:
                raise UserError("%s claim %s: nothing measured to absorb the "
                                "rounding." % (contract.code, number))
            absorber.this_qty += drift / absorber.rate
        residue = claim.gross_to_date - target
        if abs(residue) > 1.0:
            raise UserError(
                "%s claim %s: reconstructed %s against an invoice of %s."
                % (contract.code, number, claim.gross_to_date, target))

        claim._check_measurement()
        # Written straight to certified: the invoice these sheets explain is
        # already posted and numbered. Taking them through submit → certify →
        # invoice would raise a second invoice for the same work.
        claim.write({
            "state": "invoiced",
            "certified_by": CONSULTANT[contract.code],
            "certified_date": claim_date,
            "certified_amount": claim.amount_this_period,
            "consultant_ref": "CERT/%s/%02d" % (contract.code[-3:], number),
            "invoice_id": invoice.id,
            "note": "مستخلص معاد بناؤه من الفاتورة المرحّلة — لم تُنشأ أي قيود جديدة.",
        })
        if not invoice.mizan_contract_id:
            invoice.mizan_contract_id = contract.id
        report.append((contract.code, number, "reconstructed",
                       claim.gross_to_date, claim.amount_this_period,
                       claim.retention_amount, claim.net_payable,
                       invoice.name, residue))


reconstruct(villa, villa_bill, VILLA_STAGES)
reconstruct(school, school_bill, SCHOOL_STAGES)

# ================================================== claim 3 — the real thing
VILLA_CLAIM3 = {"01.02": 75, "02.02": 100, "03.02": 100, "03.04": 100,
                "03.05": 100, "04.01": 85, "07.01": 90, "09.01": 45,
                "09.02": 10, "15.01": 35, "15.02": 25, "16.01": 30}
SCHOOL_CLAIM3 = {"01.02": 64, "03.02": 70, "03.04": 65, "03.05": 65,
                 "05.01": 55, "04.01": 25, "07.01": 15, "15.01": 10,
                 "16.01": 12}
MATERIALS_ON_SITE = {"CT-2026-001": 0.0, "CT-2026-002": 185000.0}


def raise_claim(contract, bill, measured, claim_date):
    """A claim measured on its merits, then taken all the way through."""
    claim = Claim.create({
        "contract_id": contract.id,
        "date": claim_date,
        "period_start": date(2026, 7, 1) if contract == villa else date(2026, 9, 1),
        "period_end": claim_date,
        "retention_percent": contract.retention_percent,
        "materials_on_site": MATERIALS_ON_SITE[contract.code],
    })
    lines = []
    for line in bill:
        pct = measured.get(line.item_no)
        if pct is None:
            lines.append((0, 0, {"boq_line_id": line.id, "this_qty": 0.0}))
            continue
        earlier = env["mizan.progress.claim.line"].search([
            ("boq_line_id", "=", line.id),
            ("claim_id.contract_id", "=", contract.id),
            ("claim_id.sequence_no", "<", claim.sequence_no),
        ])
        previous = sum(earlier.mapped("this_qty"))
        lines.append((0, 0, {
            "boq_line_id": line.id,
            "this_qty": round(line.quantity * pct / 100.0, 3) - previous,
        }))
    claim.write({"line_ids": lines})
    claim.action_submit()
    claim.certified_by = CONSULTANT[contract.code]
    claim.consultant_ref = "CERT/%s/03" % contract.code[-3:]
    claim.action_certify()
    claim.action_create_invoice()
    claim.action_post_invoice_and_deduct()
    report.append((contract.code, claim.sequence_no, "measured",
                   claim.gross_to_date, claim.amount_this_period,
                   claim.retention_amount, claim.net_payable,
                   claim.invoice_id.name, 0.0))
    return claim


villa_claim3 = raise_claim(villa, villa_bill, VILLA_CLAIM3, date(2026, 9, 20))
school_claim3 = raise_claim(school, school_bill, SCHOOL_CLAIM3, date(2026, 9, 20))

env.cr.commit()

# ================================================================ the evidence
print()
print("=" * 78)
print("BILLS OF QUANTITIES")
print("=" * 78)
for contract in (villa, school):
    contract.invalidate_recordset()
    print("\n%s  %s" % (contract.code, contract.name))
    print("  items priced           %d" % len(contract.boq_line_ids))
    print("  bill total         %15s" % "{:,.2f}".format(contract.boq_total))
    print("  contract value     %15s" % "{:,.2f}".format(contract.contract_value))
    print("  bill vs contract       %s" % (
        "MISMATCH" if contract.boq_mismatch else "ties exactly"))
    print("  certified to date   %15s   (%.2f%% measured)" % (
        "{:,.2f}".format(contract.certified_to_date),
        contract.measured_completion_percent))
    print("  %% complete by cost         %.2f%%" % contract.completion_percent)

print()
print("=" * 78)
print("PROGRESS CLAIMS")
print("=" * 78)
print("%-12s %3s %-14s %13s %13s %11s %13s %-16s %8s" % (
    "contract", "no", "source", "gross to date", "this period",
    "retention", "net payable", "invoice", "residue"))
for row in report:
    print("%-12s %3d %-14s %13s %13s %11s %13s %-16s %8.2f" % (
        row[0], row[1], row[2],
        "{:,.2f}".format(row[3]), "{:,.2f}".format(row[4]),
        "{:,.2f}".format(row[5]), "{:,.2f}".format(row[6]), row[7], row[8]))

print()
print("=" * 78)
print("OVER-MEASUREMENT CHECK")
print("=" * 78)
over = env["mizan.progress.claim.line"].search([("is_over_measured", "=", True)])
print("claim items measuring more than the bill allows: %d" % len(over))
for line in over:
    print("   %s %s  %s of %s" % (line.claim_id.name, line.item_no,
                                  line.cumulative_qty, line.quantity))

print()
print("=" * 78)
print("CLAIM 3 — WHAT THE CONSULTANT SIGNS (%s)" % villa.code)
print("=" * 78)
print("%-8s %-34s %-6s %10s %10s %10s %8s" % (
    "item", "description", "unit", "bill qty", "prev qty", "this qty", "%"))
for line in villa_claim3.line_ids.sorted(key=lambda l: l.sequence):
    if not (line.this_qty or line.previous_qty):
        continue
    print("%-8s %-34s %-6s %10s %10s %10s %7.1f%%" % (
        line.item_no, (line.name or "")[:34], line.unit or "",
        "{:,.2f}".format(line.quantity), "{:,.2f}".format(line.previous_qty),
        "{:,.2f}".format(line.this_qty), line.percent_complete))
print("-" * 78)
print("%-60s %15s" % ("value of work done to date",
                      "{:,.2f}".format(villa_claim3.work_done_to_date)))
print("%-60s %15s" % ("less previously certified",
                      "{:,.2f}".format(villa_claim3.previous_certified)))
print("%-60s %15s" % ("value this period",
                      "{:,.2f}".format(villa_claim3.amount_this_period)))
print("%-60s %15s" % ("less retention @ %.0f%%" % villa_claim3.retention_percent,
                      "{:,.2f}".format(villa_claim3.retention_amount)))
print("%-60s %15s" % ("less advance recovery",
                      "{:,.2f}".format(villa_claim3.advance_recovery)))
print("%-60s %15s" % ("NET PAYABLE", "{:,.2f}".format(villa_claim3.net_payable)))
