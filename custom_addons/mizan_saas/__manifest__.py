{
    "name": "Miqyas Operations Console",
    "version": "1.0",
    "category": "Administration",
    "summary": "Provision, monitor, back up and suspend client deployments",
    "description": """
Every Miqyas client runs in its own database, which is what keeps one
client's ledger structurally unreachable from another's. The cost of that
isolation is that nothing inside Odoo can see across the databases: backups,
disk growth, user counts and renewals all have to be checked one deployment at
a time, by hand, which is exactly the kind of work that stops being done.

This module is the operator's console. It reads each client's figures live from
the cluster, takes and rotates their backups, provisions a new client by
copying a golden template, and suspends one by disabling logins inside their
own database rather than merely flagging it here.

Install it in the operator's own database only — never in a client's.
""",
    "depends": ["base", "mail"],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
    "data": [
        "security/saas_security.xml",
        "security/ir.model.access.csv",
        "data/config_parameters.xml",
        "data/ir_cron.xml",
        "views/tenant_views.xml",
        "views/tenant_backup_views.xml",
        "views/tenant_metric_views.xml",
        "wizards/tenant_provision_views.xml",
        "views/menus.xml",
    ],
}
