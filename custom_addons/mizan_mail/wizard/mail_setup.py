# -*- coding: utf-8 -*-
"""Connect the address invoices are sent from, in one screen.

Odoo's outgoing-server form asks for a host, a port, an encryption scheme and
an authentication method — four things an accountant should not need to know.
Here the provider is chosen and those are filled in; the person types only the
address and its password, tests, and saves. The password is stored on the mail
server record like Odoo's own form does, and never shown again.
"""
from odoo import api, fields, models, _
from odoo.exceptions import UserError

PROVIDERS = {
    "gmail": ("smtp.gmail.com", 587, "starttls"),
    "outlook": ("smtp.office365.com", 587, "starttls"),
    "hostinger": ("smtp.hostinger.com", 465, "ssl"),
    "zoho": ("smtp.zoho.com", 465, "ssl"),
}
SERVER_NAME = "Miqyas — outgoing email"


class MizanMailSetup(models.TransientModel):
    _name = "mizan.mail.setup"
    _description = "Email Setup"

    provider = fields.Selection([
        ("gmail", "Gmail / Google Workspace"),
        ("outlook", "Outlook / Microsoft 365"),
        ("hostinger", "Hostinger email"),
        ("zoho", "Zoho Mail"),
        ("custom", "Other (enter the server)"),
    ], default="gmail", required=True)
    email = fields.Char(string="Email address", required=True,
                        help="The address customers see invoices come from.")
    password = fields.Char(
        string="Password",
        help="For Gmail and Microsoft 365 this is an app password, not the "
             "normal one: create it in the account's security settings "
             "(two-step verification must be on).")
    host = fields.Char(compute="_compute_server", store=True, readonly=False)
    port = fields.Integer(compute="_compute_server", store=True, readonly=False)
    encryption = fields.Selection([("none", "None"), ("starttls", "TLS (STARTTLS)"), ("ssl", "SSL/TLS")],
                                  compute="_compute_server", store=True, readonly=False)
    server_id = fields.Many2one("ir.mail_server", readonly=True)
    status = fields.Char(readonly=True)

    @api.depends("provider")
    def _compute_server(self):
        for wiz in self:
            if wiz.provider in PROVIDERS:
                wiz.host, wiz.port, wiz.encryption = PROVIDERS[wiz.provider]
            elif not wiz.host:
                wiz.host, wiz.port, wiz.encryption = "", 465, "ssl"

    @api.model
    def action_open(self):
        server = self.env["ir.mail_server"].sudo().search([], order="sequence", limit=1)
        vals = {}
        if server:
            provider = next((k for k, v in PROVIDERS.items() if v[0] == server.smtp_host), "custom")
            vals = {"provider": provider, "email": server.smtp_user, "server_id": server.id,
                    "status": _("Connected: emails go out from %s.", server.smtp_user)}
            if provider == "custom":
                vals.update(host=server.smtp_host, port=server.smtp_port, encryption=server.smtp_encryption)
        wizard = self.create(vals) if vals else self.create({"email": self.env.company.email or ""})
        return wizard._reopen()

    def _reopen(self):
        return {"type": "ir.actions.act_window", "name": _("Email setup"),
                "res_model": self._name, "res_id": self.id,
                "view_mode": "form", "views": [[False, "form"]], "target": "new"}

    def _server_values(self):
        self.ensure_one()
        email = (self.email or "").strip()
        if "@" not in email:
            raise UserError(_("Type a full email address, for example invoices@yourcompany.ae."))
        if not self.host or not self.port:
            raise UserError(_("Enter the email server and its port."))
        vals = {
            "name": SERVER_NAME, "smtp_host": self.host.strip(), "smtp_port": self.port,
            "smtp_encryption": self.encryption, "smtp_authentication": "login",
            "smtp_user": email, "from_filter": email, "sequence": 1,
        }
        if self.password:
            vals["smtp_pass"] = self.password
        return vals

    def _write_server(self):
        Server = self.env["ir.mail_server"].sudo()
        vals = self._server_values()
        server = self.server_id or Server.search([("name", "=", SERVER_NAME)], limit=1)
        if not server and not self.password:
            raise UserError(_("Type the password for %s.", vals["smtp_user"]))
        if server:
            server.write(vals)
        else:
            server = Server.create(vals)
        self.server_id = server
        return server

    def action_test(self):
        self.ensure_one()
        server = self._write_server()
        try:
            server.test_smtp_connection()
        except UserError as error:
            self.status = _("Not connected: %s", str(error).splitlines()[0][:200])
            return self._reopen()
        self.status = _("Connection works. Press Save to send from %s.", server.smtp_user)
        return self._reopen()

    def action_save(self):
        self.ensure_one()
        server = self._write_server()
        email = server.smtp_user
        # Every email that does not come from this exact address is sent as
        # this address, with Reply-To kept — otherwise the provider rejects it.
        domain_name = email.split("@", 1)[1].lower()
        Domain = self.env["mail.alias.domain"].sudo()
        alias_domain = Domain.search([("name", "=", domain_name)], limit=1) \
            or Domain.create({"name": domain_name})
        alias_domain.default_from = email
        company = self.env.company.sudo()
        company.alias_domain_id = alias_domain
        if not company.email:
            company.email = email
        return {
            "type": "ir.actions.client", "tag": "display_notification",
            "params": {"title": _("Email is set up"),
                       "message": _("Invoices and reminders now go out from %s.", email),
                       "type": "success", "next": {"type": "ir.actions.act_window_close"}},
        }

    def action_remove(self):
        self.ensure_one()
        if self.server_id:
            self.server_id.sudo().unlink()
        return {"type": "ir.actions.act_window_close"}
