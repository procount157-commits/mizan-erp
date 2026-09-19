# -*- coding: utf-8 -*-
"""شركة الأمانة للمقاولات — staff, roles and the petty cash approval chain.

Run against the client's own database, after provisioning it from the template:

    docker compose exec -T odoo odoo shell --config=/etc/odoo/odoo.conf \
        --db_user odoo --db_password "$PW" -d alamana --no-http \
        < scripts/clients/setup_alamana.py

The petty cash rule this sets up: an engineer or the accountant spends, the
general manager approves, and only then can the accountant post it to the
ledger and pay it out of the petty cash box. Nobody approves their own
spending — which is the whole point of the control, and the reason the
approver is set on each employee record rather than left to Odoo's default of
"whoever is above you in the org chart".
"""
from datetime import date, timedelta

company = env.company
AED = company.currency_id


def gid(xmlid):
    return env.ref(xmlid).id


def groups(*xmlids):
    return [(6, 0, [gid(x) for x in xmlids])]


# --------------------------------------------------------------- the company
company.write({
    "street": "مكتب 1204، برج الأعمال، شارع الشيخ زايد",
    "city": "دبي",
    "country_id": env.ref("base.ae").id,
    "phone": "+971 4 555 0100",
    "email": "info@alamana.ae",
    "website": "https://alamana.ae",
})
print("company: %s" % company.name)

# --------------------------------------------------------------- departments
Dept = env["hr.department"]


def department(name):
    found = Dept.search([("name", "=", name)], limit=1)
    return found or Dept.create({"name": name, "company_id": company.id})


d_exec = department("الإدارة العامة")
d_fin = department("المالية والحسابات")
d_eng = department("الهندسة والمشاريع")

# -------------------------------------------------------------------- people
# Role → the groups that role actually needs. Deliberately not "administrator
# for everyone": a finance manager who can also change system settings, or an
# engineer who can post journal entries, is how a small company loses the
# separation of duties it is paying for.
PEOPLE = [
    {
        "key": "gm",
        "name": "سالم الشامسي",
        "login": "manager@alamana.ae",
        "password": "Amana#Mgr2026",
        "job": "المدير العام",
        "dept": d_exec,
        # Full sight of the numbers and every approval, without the system
        # settings — those stay with the finance manager and the administrator.
        "groups": (
            "base.group_user",
            "hr_expense.group_hr_expense_user",          # approves any expense
            "project.group_project_manager",
            "hr_timesheet.group_timesheet_manager",
            "purchase.group_purchase_manager",
            "purchase_request.group_purchase_request_manager",
            "sales_team.group_sale_manager",
            "hr.group_hr_manager",
            "account.group_account_manager",             # sees and signs off everything
            "account.group_account_user",
            "account.group_account_readonly",
            "account.group_account_invoice",
            "analytic.group_analytic_accounting",
            "base.group_multi_currency",
        ),
    },
    {
        "key": "cfo",
        "name": "ندى القاسمي",
        "login": "finance@alamana.ae",
        "password": "Amana#Fin2026",
        "job": "المدير المالي",
        "dept": d_fin,
        # Everything, deliberately. In a company this size the finance manager
        # is the person who closes the books, answers the auditor and owns the
        # configuration, so anything hidden from them is an obstacle rather
        # than a control. System settings included.
        "groups": (
            "base.group_user",
            "base.group_system",
            "account.group_account_manager",
            "account.group_account_user",
            "account.group_account_readonly",
            "account.group_account_invoice",
            "account.group_account_secured",
            "hr_expense.group_hr_expense_manager",
            "purchase.group_purchase_manager",
            "purchase_request.group_purchase_request_manager",
            "project.group_project_manager",
            "hr_timesheet.group_timesheet_manager",
            "sales_team.group_sale_manager",
            "hr.group_hr_manager",
            "analytic.group_analytic_accounting",
            "base.group_multi_currency",
        ),
    },
    {
        "key": "acc",
        "name": "يوسف حيدر",
        "login": "accountant@alamana.ae",
        "password": "Amana#Acc2026",
        "job": "محاسب",
        "dept": d_fin,
        "groups": (
            "base.group_user",
            "account.group_account_user",                # posts entries
            "account.group_account_invoice",
            "account.group_account_readonly",            # all financial reports
            "purchase.group_purchase_user",
            "purchase_request.group_purchase_request_user",
            "sales_team.group_sale_salesman_all_leads",
            "hr_expense.group_hr_expense_team_approver",
            "analytic.group_analytic_accounting",
            "base.group_multi_currency",
        ),
    },
    {
        "key": "eng1",
        "name": "عمر خليل",
        "login": "eng.omar@alamana.ae",
        "password": "Amana#Eng1-2026",
        "job": "مهندس موقع أول",
        "dept": d_eng,
        "groups": (
            "base.group_user",
            "project.group_project_user",
            "hr_timesheet.group_hr_timesheet_user",
            "purchase_request.group_purchase_request_user",
            "analytic.group_analytic_accounting",
        ),
    },
    {
        "key": "eng2",
        "name": "ليلى منصور",
        "login": "eng.laila@alamana.ae",
        "password": "Amana#Eng2-2026",
        "job": "مهندس مدني",
        "dept": d_eng,
        "groups": (
            "base.group_user",
            "project.group_project_user",
            "hr_timesheet.group_hr_timesheet_user",
            "purchase_request.group_purchase_request_user",
            "analytic.group_analytic_accounting",
        ),
    },
    {
        "key": "eng3",
        "name": "طارق عبدالله",
        "login": "eng.tariq@alamana.ae",
        "password": "Amana#Eng3-2026",
        "job": "مهندس كهروميكانيك",
        "dept": d_eng,
        "groups": (
            "base.group_user",
            "project.group_project_user",
            "hr_timesheet.group_hr_timesheet_user",
            "purchase_request.group_purchase_request_user",
            "analytic.group_analytic_accounting",
        ),
    },
]

Users = env["res.users"]
Emp = env["hr.employee"]
users = {}
employees = {}

for person in PEOPLE:
    existing = Users.with_context(active_test=False).search(
        [("login", "=", person["login"])], limit=1)
    if existing:
        user = existing
        user.write({"groups_id": groups(*person["groups"])})
    else:
        user = Users.create({
            "name": person["name"],
            "login": person["login"],
            "password": person["password"],
            "lang": "ar_001",
            "tz": "Asia/Dubai",
            "company_id": company.id,
            "company_ids": [(6, 0, [company.id])],
            "groups_id": groups(*person["groups"]),
        })
    users[person["key"]] = user

    employee = Emp.search([("user_id", "=", user.id)], limit=1)
    values = {
        "name": person["name"],
        "user_id": user.id,
        "job_title": person["job"],
        "department_id": person["dept"].id,
        "work_email": person["login"],
        "company_id": company.id,
    }
    if employee:
        employee.write(values)
    else:
        employee = Emp.create(values)
    employees[person["key"]] = employee
    print("user: %-22s %-28s %s" % (person["name"], person["login"], person["job"]))

# ------------------------------------------------- who approves whose spending
# The general manager approves petty cash for the engineers AND the accountant.
# Setting expense_manager_id explicitly matters: left empty, Odoo falls back to
# the employee's line manager, so the accountant's claims would route to the
# finance manager and never reach the general manager at all.
gm_user = users["gm"]
for key in ("acc", "eng1", "eng2", "eng3"):
    employee = employees[key]
    if "expense_manager_id" in employee._fields:
        employee.expense_manager_id = gm_user.id
    employee.parent_id = employees["gm" if key == "acc" else "eng1"].id
employees["eng1"].parent_id = employees["gm"].id
employees["cfo"].parent_id = employees["gm"].id
employees["acc"].parent_id = employees["cfo"].id
if "expense_manager_id" in employees["cfo"]._fields:
    employees["cfo"].expense_manager_id = gm_user.id
print("petty cash approver for accountant and all engineers: %s" % gm_user.name)

env.cr.commit()

# ----------------------------------------------------------- the petty cash box
Account = env["account.account"]


def account_by_code(code):
    return Account.search([("code", "=", code)], limit=1)


petty_account = account_by_code("101020")
if not petty_account:
    values = {
        "code": "101020",
        "name": "الصندوق النثري",
        "account_type": "asset_current",
    }
    # Odoo 18 made account.account multi-company; older field name kept as a
    # fallback so this script survives either.
    if "company_ids" in Account._fields:
        values["company_ids"] = [(6, 0, [company.id])]
    else:
        values["company_id"] = company.id
    petty_account = Account.create(values)

Journal = env["account.journal"]
petty_journal = Journal.search([("code", "=", "PTY")], limit=1)
if not petty_journal:
    petty_journal = Journal.create({
        "name": "الصندوق النثري",
        "code": "PTY",
        "type": "cash",
        "company_id": company.id,
        "default_account_id": petty_account.id,
    })
# Send payments straight to the cash account instead of an outstanding one.
# Outstanding accounts model money that has left the company but not yet the
# bank — a cheque in the post. Physical cash has no such gap: it leaves the box
# the moment it is handed over, and a petty cash box whose balance never moves
# cannot be counted against the drawer, which is the only control there is.
for method in (petty_journal.outbound_payment_method_line_ids
               | petty_journal.inbound_payment_method_line_ids):
    method.payment_account_id = petty_account.id

print("petty cash journal: %s (%s), payments post straight to the box"
      % (petty_journal.name, petty_account.code))

# Posting an expense needs somewhere to park what the company still owes the
# employee. Without it the accountant hits a wall at the last step, which is
# exactly where it is most confusing.
if "expense_outstanding_account_id" in company._fields:
    if not company.expense_outstanding_account_id:
        company.expense_outstanding_account_id = account_by_code("101004")

# ------------------------------------------------------------- the float
# A petty cash box starts with money in it. Without an opening float the box
# runs negative on the first claim, which reads as an error to the person
# counting the drawer even though the accounting is sound.
float_ref = "افتتاح عهدة الصندوق النثري"
if not env["account.move"].search([("ref", "=", float_ref)], limit=1):
    bank_journal = Journal.search(
        [("type", "=", "bank"), ("company_id", "=", company.id)], limit=1)
    general = Journal.search(
        [("type", "=", "general"), ("company_id", "=", company.id)], limit=1)
    bank_account = bank_journal.default_account_id or account_by_code("101001")
    if bank_account and general:
        opening = env["account.move"].create({
            "journal_id": general.id,
            "ref": float_ref,
            "date": date.today().replace(day=1),
            "line_ids": [
                (0, 0, {"account_id": petty_account.id, "name": float_ref,
                        "debit": 5000.0, "credit": 0.0}),
                (0, 0, {"account_id": bank_account.id, "name": float_ref,
                        "debit": 0.0, "credit": 5000.0}),
            ],
        })
        opening.action_post()
        print("petty cash float: 5,000 AED from %s" % bank_account.code)

# ------------------------------------------------------- expense categories
Product = env["product.product"]
# Each category is pinned to a real account. Left unset, Odoo books petty cash
# to "Cost of Goods Sold in Trading", so a contractor's fuel and permit
# receipts pile up in a trading account and the project cost is wrong — which
# is worse than useless on a percentage-of-completion contract.
CATEGORIES = [
    ("مصروف نثري عام", "PC-GEN", "400050"),
    ("وقود ومواصلات", "PC-FUEL", "401005"),
    ("مواد وأدوات موقع", "PC-SITE", "401001"),
    ("ضيافة واستقبال", "PC-HOSP", "400047"),
    ("رسوم حكومية وتصاريح", "PC-GOV", "401009"),
]
expense_products = {}
for name, code, account_code in CATEGORIES:
    product = Product.search([("default_code", "=", code)], limit=1)
    if not product:
        product = Product.create({
            "name": name,
            "default_code": code,
            "type": "service",
            "can_be_expensed": True,
            "list_price": 0.0,
            "standard_price": 0.0,
        })
    account = account_by_code(account_code)
    if account and "property_account_expense_id" in product._fields:
        product.property_account_expense_id = account.id
    expense_products[code] = product
for code, product in expense_products.items():
    booked = product.property_account_expense_id
    print("expense category: %-22s -> %s %s" % (
        product.name, booked.code or "?", booked.name or ""))

# ------------------------------------------------------- customers and projects
Partner = env["res.partner"]


def customer(name, city, trn=False):
    found = Partner.search([("name", "=", name)], limit=1)
    if found:
        return found
    return Partner.create({
        "name": name,
        "is_company": True,
        "city": city,
        "country_id": env.ref("base.ae").id,
        "vat": trn,
        "customer_rank": 1,
    })


client_a = customer("شركة الخليج للاستثمار العقاري", "دبي", "100123456700003")
client_b = customer("بلدية الشارقة — إدارة المشاريع", "الشارقة")

Plan = env["account.analytic.plan"]
plan = Plan.search([], limit=1) or Plan.create({"name": "المشاريع"})
Analytic = env["account.analytic.account"]
Project = env["project.project"]


def project_with_analytic(name, partner, manager_user):
    analytic = Analytic.search([("name", "=", name)], limit=1)
    if not analytic:
        analytic = Analytic.create({
            "name": name,
            "plan_id": plan.id,
            "partner_id": partner.id,
            "company_id": company.id,
        })
    project = Project.search([("name", "=", name)], limit=1)
    if not project:
        values = {
            "name": name,
            "partner_id": partner.id,
            "user_id": manager_user.id,
            "company_id": company.id,
        }
        if "allow_timesheets" in Project._fields:
            values["allow_timesheets"] = True
        project = Project.create(values)
    # The analytic field was renamed between versions; set whichever exists so
    # costs actually land on the project rather than silently nowhere.
    for fname in ("account_id", "analytic_account_id"):
        if fname in Project._fields:
            project[fname] = analytic.id
            break
    return project, analytic


proj_villa, an_villa = project_with_analytic(
    "فيلا سكنية — ند الشبا", client_a, users["eng1"])
proj_school, an_school = project_with_analytic(
    "توسعة مدرسة — الشارقة", client_b, users["eng3"])
print("projects: %s | %s" % (proj_villa.name, proj_school.name))

# ----------------------------------------------------------------- contracts
Contract = env["mizan.contract"]
today = date.today()


def contract(code, name, partner, project, analytic, value, budget):
    found = Contract.search([("code", "=", code)], limit=1)
    if found:
        return found
    return Contract.create({
        "code": code,
        "name": name,
        "partner_id": partner.id,
        "project_id": project.id,
        "analytic_account_id": analytic.id,
        "date_start": today - timedelta(days=90),
        "date_end": today + timedelta(days=275),
        "contract_value": value,
        "budget_cost": budget,
        "retention_percent": 5.0,
        "state": "running",
    })


c1 = contract("CT-2026-001", "عقد إنشاء فيلا سكنية — ند الشبا",
              client_a, proj_villa, an_villa, 2400000.0, 1850000.0)
c2 = contract("CT-2026-002", "عقد توسعة مدرسة — الشارقة",
              client_b, proj_school, an_school, 5600000.0, 4400000.0)
print("contracts: %s (%s) | %s (%s)" % (
    c1.code, c1.contract_value, c2.code, c2.contract_value))

env.cr.commit()
