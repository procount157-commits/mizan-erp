# -*- coding: utf-8 -*-
"""Materials asked for from the site, approved from the manager's phone.

The engineer lists what he needs (cement 50 bags, rebar 2 tonnes), for which
project and by when; it becomes a purchase request against the project's
cost centre, waiting for the manager. Approved, it goes to whoever buys —
and the engineer is told either way. The purchase order itself stays in the
office: the phone asks and approves, it does not buy."""
from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .approvals import _is_manager
from .notify import _managers, tell


UNITS = [("uom.product_uom_unit", "Pieces"), ("uom.product_uom_meter", "Metres"), ("uom.uom_square_meter", "Square metres"),
         ("uom.product_uom_cubic_meter", "Cubic metres"), ("uom.product_uom_kgm", "Kilograms"),
         ("uom.product_uom_ton", "Tonnes"), ("uom.product_uom_litre", "Litres")]


class MizanMobile(models.AbstractModel):
    _inherit = "mizan.mobile"

    @api.model
    def _material_state_label(self, state):
        return {"draft": _("Draft"), "to_approve": _("Waiting for the manager"), "approved": _("Approved — to buy"),
                "in_progress": _("Being bought"), "done": _("Bought"), "rejected": _("Refused")}.get(state, state)

    @api.model
    def _material_lines_text(self, request, limit=4):
        parts = ["%s %s %s" % (l.name or l.product_id.name or "", "{:g}".format(l.product_qty),
                               l.product_uom_id.name or "") for l in request.line_ids[:limit]]
        more = len(request.line_ids) - limit
        return "، ".join(p.strip() for p in parts) + (_(" and %s more", more) if more > 0 else "")

    @api.model
    def material_form(self):
        if "engineer" not in self._roles():
            raise AccessError(_("Material requests are for site engineers."))
        contracts = self._engineer_contracts().filtered(lambda c: c.project_id and c.analytic_account_id)
        uoms = []
        for xmlid, label in UNITS:
            uom = self.env.ref(xmlid, raise_if_not_found=False)
            if uom:
                uoms.append({"id": uom.id, "name": _(label)})
        Request = self.env["purchase.request"]
        recent = Request.search([("requested_by", "=", self.env.uid)], order="id desc", limit=10)
        products = self.env["product.product"].search(
            [("purchase_ok", "=", True), ("type", "!=", "service")], order="name", limit=200)
        return {
            "projects": [{"id": c.id, "name": c.name} for c in contracts],
            "uoms": uoms,
            "products": [{"id": p.id, "name": p.name, "uom_id": p.uom_po_id.id or p.uom_id.id} for p in products],
            "recent": [{"id": r.id, "name": r.name, "what": self._material_lines_text(r), "state": r.state,
                        "state_label": self._material_state_label(r.state), "project": r.origin or "",
                        "date": r.date_start.strftime("%d/%m") if r.date_start else ""} for r in recent],
        }

    @api.model
    def submit_material_request(self, contract_id, lines, needed_by=None, note=None):
        if "engineer" not in self._roles():
            raise AccessError(_("Material requests are for site engineers."))
        contract = self.env["mizan.contract"].sudo().browse(int(contract_id)).exists()
        if not contract or not contract.analytic_account_id:
            raise UserError(_("Choose the project."))
        clean = [l for l in (lines or []) if (l.get("name") or l.get("product_id")) and float(l.get("qty") or 0) > 0]
        if not clean:
            raise UserError(_("Add at least one item with its quantity."))
        day = fields.Date.to_date(needed_by) if needed_by else fields.Date.context_today(self)
        units = self.env.ref("uom.product_uom_unit")
        managers = _managers(self.env)
        manager_users = self.env["res.users"].sudo().search([("partner_id", "in", managers.ids)], limit=1)
        values = {
            "requested_by": self.env.uid, "origin": contract.name, "description": note or False,
            "line_ids": [(0, 0, {
                "product_id": int(l["product_id"]) if l.get("product_id") else False,
                "name": (l.get("name") or "").strip() or False,
                "product_qty": float(l["qty"]),
                "product_uom_id": int(l.get("uom_id") or 0) or units.id,
                "date_required": day,
                "analytic_distribution": {str(contract.analytic_account_id.id): 100},
                "specifications": l.get("note") or False,
            }) for l in clean],
        }
        if manager_users:
            values["assigned_to"] = manager_users.id
        request = self.env["purchase.request"].create(values)
        for line in request.line_ids.filtered(lambda l: not l.name and l.product_id):
            line.name = line.product_id.display_name
        request.button_to_approve()
        tell(request, managers, _("Materials requested for %s", contract.name),
             _("%(who)s asks for %(what)s, needed by %(day)s.", who=self.env.user.name,
               what=self._material_lines_text(request), day=day.strftime("%d/%m/%Y")))
        return {"ok": True, "name": request.name, "form": self.material_form()}


class PurchaseRequest(models.Model):
    _inherit = "purchase.request"

    def _mizan_tell_outcome(self, approved):
        Mobile = self.env["mizan.mobile"]
        buyers = self.env["res.users"]
        group = self.env.ref("purchase_request.group_purchase_request_manager", raise_if_not_found=False)
        if group:
            buyers = group.sudo().users.filtered(lambda u: u.active and not u.share and u.mizan_app_role != "engineer")
        for request in self:
            what = Mobile._material_lines_text(request)
            if request.requested_by:
                tell(request, request.requested_by.partner_id,
                     _("Your material request is approved") if approved else _("Your material request was refused"),
                     _("%(name)s: %(what)s.", name=request.name, what=what))
            if approved and buyers:
                tell(request, buyers.partner_id, _("Approved materials to buy"),
                     _("%(name)s for %(project)s: %(what)s. Make the purchase order.", name=request.name,
                       project=request.origin or "", what=what))

    def button_approved(self):
        res = super().button_approved()
        self._mizan_tell_outcome(True)
        return res

    def button_rejected(self):
        res = super().button_rejected()
        self._mizan_tell_outcome(False)
        return res
