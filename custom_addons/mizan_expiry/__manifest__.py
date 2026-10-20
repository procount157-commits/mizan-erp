# -*- coding: utf-8 -*-
{
    "name": "Miqyas Expiries",
    "version": "1.0",
    "category": "Human Resources",
    "summary": "Every licence, insurance policy, visa, Emirates ID and vehicle registration, with its expiry date and a warning before it lapses",
    "description": """A contractor in the UAE lives on dates: the trade licence, the civil defence
and municipality certificates, the contractor's all-risk and workmen's
compensation policies, every worker's residence visa, Emirates ID, passport and
labour card, each vehicle's registration and each crane's inspection. One that
lapses stops a site, blocks a payment run or brings a fine.

* One register of everything that expires, with the document attached and who
  is responsible for renewing it.
* Workers' visas, labour cards, Emirates IDs, passports and medical insurance
  come straight from the employee record; subcontractors' insurance from the
  subcontract. Nothing is typed twice.
* A warning before the date (each kind has its own notice: 60 days for a
  licence, 30 for a visa), again a week before, and on the day it lapses — to
  the person responsible and to the managers, on the phone.
* Renewal in one step: the new dates, the cost, the history kept.
* The owner's page and the phone show what lapses this month.
""",
    "author": "ProAccount",
    "depends": ["hr", "mail", "mizan_owner", "mizan_contracting"],
    "data": [
        "security/ir.model.access.csv",
        "data/cron.xml",
        "views/expiry_views.xml",
        "views/hr_employee_views.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
