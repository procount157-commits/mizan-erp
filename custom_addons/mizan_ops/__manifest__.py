# -*- coding: utf-8 -*-
{
    "name": "Miqyas Operations",
    "version": "1.0",
    "category": "Project",
    "summary": "Team workflows, tasks and files — the shared document replaced by a system",
    "description": """The office ran its work in a shared document: who is doing what for which
client, which papers arrived, what is still missing. It worked until two
people edited it at once, or a file was in somebody's phone.

Operations turns that document into a system built on the project tasks the
company already has:

* Workflow templates — the steps a recurring job always takes (a licence
  renewal, a quarterly VAT return, a project handover), with who does each
  step, how many days it gets, and whether it needs a file.
* Start a workflow for a client or project and every step becomes a task,
  assigned and dated, with the whole file's progress in one bar.
* Files live on the task or the workflow they belong to, uploaded from the
  phone in one screen, and found again from one documents list.
* My tasks, from the phone: what is mine, what is late, done with one tap.
""",
    "author": "ProAccount",
    "depends": ["project", "mail", "mizan_hub"],
    "data": [
        "security/ops_security.xml",
        "security/ir.model.access.csv",
        "data/ops_project.xml",
        "data/templates.xml",
        "views/template_views.xml",
        "views/case_views.xml",
        "views/task_views.xml",
        "wizard/start_views.xml",
        "wizard/upload_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
