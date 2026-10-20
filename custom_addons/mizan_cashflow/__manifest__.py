# -*- coding: utf-8 -*-
{
    "name": "Miqyas Cash Flow Forecast",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "The next thirteen weeks of cash, week by week: what comes in, what goes out, and the week it runs short",
    "description": """A contractor is rarely short of profit and often short of cash: the client
pays sixty days late, the subcontractors and the payroll do not wait. This
shows, week by week for thirteen weeks, the cash in the banks and what the
books already know will move it:

* customers' invoices by due date (late ones in the first week, marked late);
* supplier bills by due date;
* post-dated cheques received and issued, by their date — without counting
  the invoice they settle a second time;
* the payroll at each month end, from the running employment contracts;
* the VAT return due on the 28th after each quarter;
* subcontractor payments waiting for approval;
* retention the clients hold, half at completion and half after the
  defects year (an estimate, marked as one).

The lowest week is on the owner's page and the phone. Rebuilt every night and
on demand. Every figure opens the documents behind it.
""",
    "author": "ProAccount",
    "depends": ["account", "hr_contract", "mizan_owner", "mizan_cheque", "mizan_project_accounts"],
    "data": [
        "security/ir.model.access.csv",
        "data/cron.xml",
        "views/forecast_views.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
