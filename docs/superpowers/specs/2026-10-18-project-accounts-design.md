# Project accounts: the CFO's way of running contract books

Date: 2026-10-18. Requested by the client's CFO (الأمانة), relayed by the owner.
Builder: Claude, in `custom_addons/mizan_project_accounts`, on top of
`mizan_contracting`, `mizan_pettycash`, `mizan_site`, `stock_account`, `payroll`.

## Intent

Every project must be readable from the chart of accounts itself: what it
billed, what it cost, what the client still holds, what the client owes.
Every dirham of cost must say where it came from (supplier bill, petty cash,
subcontractor, labour card, stock issue, direct entry). Entry screens must do
the bookkeeping: the engineer, the storekeeper and the cashier type facts;
the system writes the entries. IFRS 15 (percentage of completion) throughout.

## What exists already (kept, extended)

- `mizan.contract` with value, retention %, advance %, analytic cost centre,
  bill of quantities and measured progress claims (`mizan.progress.claim`),
  retention withholding on invoices, cost-to-cost revenue recognition
  (`mizan.contract.recognition`), subcontracts with retention, cost codes,
  budgets, WIP figures, plant charges, overhead allocation.
- Petty cash: photograph → claim → approve → post → advance settled.
- Site reports with timesheets. Stock, stock_account (manual valuation),
  payroll, hr_contract installed.

What is missing is listed per workstream below.

## Goals / non-goals / anti-goals

Goals: the six workstreams below, each usable from a phone where the person
works on site. Non-goals: multi-currency contracts, consolidated reporting,
changing Odoo's own invoice screens. Anti-goals: any figure computed by AI;
any entry the accountant cannot trace to a screen and a person.

## Design

### Accounts created with the project

On `mizan.contract.action_start` (and a button for contracts already
running) the system creates, in order, and links on the contract:

| Field on contract | Code | Name (Arabic on the account) | Type | Group |
|---|---|---|---|---|
| `receivable_account_id` | 1021NN | عميل – <project> | asset_receivable, reconcile | 102 الذمم المدينة |
| `billing_account_id` | 1071NN | فوترة – <project> | asset_current | 107 أصول العقود |
| `wip_account_id` | 1072NN | تكاليف تحت التنفيذ – <project> | asset_current | 107 |
| `retention_account_id` | 1073NN | محتجزات العميل – <project> | asset_current, reconcile | 107 |
| `cost_account_id` | 4011NN | تكلفة العقد – <project> | expense_direct_cost | 401 |

NN = next free two-digit suffix, the same for the five. Codes are six
digits like the rest of the chart. Also created when missing: the analytic
account (named after the contract) and the `project.project` linked to it,
so site reports, petty cash and tasks all land on the same cost centre; and
a stock location "موقع – <project>" (usage production) under the warehouse's
view location, for stock issues.

Company-level accounts, created on install if absent: 107900 "دفعات مقدمة من
العملاء – وسيط" (asset_current; always nets to zero), 201090 "أجور عمال
المواقع المستحقة" (liability_current), 203 group "مقاولو الباطن".

### Cost routing (the one rule)

In `account.move.line` create/write, for product lines of draft moves: when
the line belongs to a contract (move.mizan_contract_id, or its analytic
distribution names a contract's analytic account) and its account is a P&L
expense account, the account becomes the contract's `wip_account_id` and the
cost code is taken from the original account when a cost code maps to it.
The analytic distribution is kept. This single rule serves supplier bills,
subcontractor bills, petty-cash claims, employee expenses, direct journal
entries and payroll analytic lines. Lines that already sit on a contract
account are left alone. Plant and overhead allocations stay analytic-only.

Cost incurred for a contract = debit balance of `wip_account_id` + cost
already transferred to `cost_account_id` (so recognition and the WIP screen
read the ledger, not the analytic lines).

### Billing modes and recognition

`mizan.contract.billing_mode`:

- **progress** (default): claims measure cumulative work; each claim invoice
  states cumulative value, previous, this period. On invoice post the system
  creates and posts a recognition for the claim's cumulative percent.
- **schedule**: invoices follow the payment schedule and say nothing about
  progress; the percent complete is typed in the "Progress to date" window
  (`mizan.contract.recognition` with `source = measured`), which posts the
  recognition.

The existing cost-to-cost recognition remains available as `source = cost`.

Claim invoice entry (both modes): Dr customer (contract receivable account)
gross / Cr `billing_account_id` net / Cr VAT 5%. Payment-term line account
is set to the contract's receivable account before posting.

Recognition entry, on post, for the percent given:
- revenue: Dr `billing_account_id` / Cr 501001 contract revenue, for
  (contract value × cumulative %) − revenue already recognised;
- cost: Dr `cost_account_id` / Cr `wip_account_id`, for the WIP balance not
  yet transferred.
If the revenue figure is negative (percent revised down) the entry is
reversed in sign and flagged on the record. A balance left on the billing
account is the over/under-billing, read directly by the WIP screen.

Progress invoice statement (PDF, `report_progress_statement`): per claim,
the cumulative-to-date, previously certified, this period, retention,
advance recovered, net; and the contract's running totals across years.

### Customer advance

Wizard "استلام دفعة مقدمة" (`mizan.customer.advance`): customer, contract,
date, bank journal, amount, reference. Posts two entries tagged with the
contract: (1) Dr 107900 clearing / Cr contract receivable; (2) Dr bank /
Cr 107900 clearing. The clearing account therefore reads zero at all times;
the customer's account carries the credit, which later offsets claim
invoices (reconciled on the payment screen or by the auto-matcher). The
advance register (PDF and list) lists advances per contract and customer
against percent complete. The old `action_record_advance` (204002) is
hidden on contracts that have the new accounts.

### Customer payment with retention

Wizard "تسجيل سداد عميل" (`mizan.customer.payment`): customer, contract,
open invoices (optional, multi), date, bank journal, amount received,
retention withheld (default: contract retention % of the invoices' gross,
less retention already withheld on them). Entry: Dr bank (received) / Dr
contract retention account (withheld) / Cr contract receivable (sum),
reconciled with the chosen invoices. "إفراج عن محتجزات" wizard posts Dr
receivable / Cr retention account when the client releases them, so the
retention account is a ledger of what each client still holds.

### Subcontractors, on their own

On `mizan.subcontract` creation (or marking a partner "مقاول باطن") the
system creates 2031NN "مقاول باطن – <name>" (liability_payable, reconcile)
and 2041NN "محتجزات – <name>" (liability_current, reconcile), one pair per
partner, and sets the partner's payable account to 2031NN. A subcontractor
bill then posts Dr project WIP (via the routing rule) / Cr 2031NN. Wizard
"سداد مقاول باطن": bill(s), amount paid, retention withheld (default
subcontract %) → Dr 2031NN / Cr bank / Cr 2041NN, reconciled. "إفراج عن
محتجزات مقاول" → Dr 2041NN / Cr 2031NN. `action_close` then works.

### Labour cards

`mizan.labour.card`: one per worker (hr.employee) with `daily_wage`
(from the HR contract wage / 30 when present, else typed). `mizan.labour.day`
lines: date, contract, fraction of day (1, 0.5, or hours/8), cost = wage ×
fraction. Entered from "كروت العمال" (editable list, grouped by day; the
engineer enters the day's crew from the phone) and from the site report.
"ترحيل اليوم" posts one entry per day per contract: Dr project WIP / Cr
201090 accrued site wages, with the analytic. Payroll settles 201090 when
salaries are paid (noted in the accountant's guide; no payroll change).

### Stock issues to projects

Supplier bills of stockable products hit inventory (product category
expense account = stock valuation account, set on install for the stockable
categories; purchase receipts as standard). Issue voucher "سند صرف مخزون"
(`mizan.stock.issue`): contract, responsible (engineer or storekeeper),
lines product/qty. Confirming creates and validates a picking from
WH/Stock to the project's location, then posts Dr project WIP / Cr inventory
for the value of the moves' valuation layers (manual valuation keeps no
entries of its own). The voucher prints with the responsible's name.

### Project card and ledger

Contracting → "المشاريع" kanban: one card per running contract with billed,
cost (WIP + recognised), client balance, retention held, advances received,
percent complete, margin. Tapping a figure opens the lines. "دفتر المشروع"
lists every journal item on the five accounts with a Source column computed
from the move: فاتورة مورد / مقاول باطن / عهدة / كارت عمال / صرف مخزون /
قيد مباشر / رواتب / مستخلص / دفعة مقدمة / سداد. Printable project statement.

### Reports (QWeb PDF, A4, Arabic/English)

Progress invoice statement; project statement (ledger by source); advances
register; client retention register; subcontractor retention register. All
read the ledger accounts, never the analytic lines, so they tie to the
trial balance.

## Constraints

- Six-digit account codes; groups by prefix as the chart already does.
- Entries only on posted, auditable moves; every wizard is a screen a person
  fills, and every move names the contract.
- Nothing changes for contracts without the new accounts until the
  "Create project accounts" button is pressed.
- Arabic first in every label, English kept as the source string.

## Left to the builder

Exact field names, the order of menus inside the Contracting app, the card
layout, the report layout, test fixtures. Where the CFO's text and IFRS 15
differ (costs are expensed as incurred under output methods), the entry
follows IFRS 15 and the screen label says so.

## Delivery order

1. Accounts per contract, cost routing, project card and ledger.
2. Billing modes, claim invoice accounts, recognition entries, progress
   statement.
3. Advance and payment wizards, retention release, registers.
4. Subcontractor accounts and wizards.
5. Labour cards.
6. Stock issue vouchers.

Each step is tested on a copy of the client database, then deployed.
