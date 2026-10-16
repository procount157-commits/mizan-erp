# -*- coding: utf-8 -*-
{
    "name": "Miqyas Bank Statement PDF",
    "version": "1.0",
    "category": "Accounting/Accounting",
    "summary": "Import the bank's PDF statement and reconcile it automatically",
    "description": """Banks hand over PDFs. The import screen took CSV, Excel and CAMT only, so the
statement was retyped. This reads the PDF itself:

* rows are rebuilt from where each word sits on the page, so any bank's
  table layout is read, not one bank's;
* each row's direction comes from the running balance, not from guessing
  which column is debit and which is credit;
* the statement is accepted only if every row's amount equals the change in
  balance and the opening balance plus the rows equals the closing one —
  otherwise it is refused, naming the row that did not add up. Nothing is
  guessed, so a misread figure never reaches the ledger.

Imported lines go through the automatic matching already in Miqyas: what is
certain is reconciled at once, the rest waits with its proposal.
""",
    "author": "ProAccount",
    "depends": ["account_statement_import_file", "mizan_core"],
    "external_dependencies": {"python": ["pdfminer"]},
    "data": ["views/import_views.xml", "data/bank_rules.xml"],
    "post_init_hook": "post_init_hook",
    "installable": True,
    "application": False,
    "license": "LGPL-3",
}
