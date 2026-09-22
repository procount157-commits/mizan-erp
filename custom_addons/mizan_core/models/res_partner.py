# -*- coding: utf-8 -*-
"""Give a UAE partner its emirate, because VAT silently depends on it.

l10n_ae ships one auto-applying fiscal position per emirate, matched on the
partner's STATE, plus a catch-all "Non-UAE" that maps 5% to 0% on sales and to
reverse charge on purchases. The catch-all has no country and no state, so it
matches anything the emirate positions do not — including a UAE partner whose
emirate was simply never filled in.

The result is the worst kind of bug: nothing errors, nothing looks wrong, and
every domestic sale is quietly zero-rated. On this database all nine partners
carried country AE and no emirate, so every invoice a human typed would have
gone out at 0% output VAT. The historical invoices are correct only because
they were written by scripts that set the tax explicitly and never ran the
onchange.

So the emirate is derived from the city whenever the city names one. It is not
guessed: a partner whose city says nothing keeps an empty emirate and shows up
in the review list, because inventing an emirate would put the revenue in the
wrong box of the VAT return, which is a different wrong answer rather than a
fixed one.
"""

from odoo import api, models

# City spellings to the emirate's ISO code, in both languages and the
# spellings people actually type.
EMIRATE_BY_CITY = {
    "DU": ("dubai", "دبي", "دبى", "bur dubai", "deira", "jebel ali",
           "nad al sheba", "ند الشبا", "البرشاء", "barsha"),
    "AZ": ("abu dhabi", "abudhabi", "أبوظبي", "ابوظبي", "أبو ظبي",
           "ابو ظبي", "al ain", "العين", "مصفح", "mussafah"),
    "SH": ("sharjah", "الشارقة", "الشارقه", "muwaileh", "مويلح"),
    "AJ": ("ajman", "عجمان"),
    "UQ": ("umm al quwain", "umm al-quwain", "أم القيوين", "ام القيوين"),
    "RK": ("ras al khaimah", "ras al-khaimah", "rak", "رأس الخيمة",
           "راس الخيمة"),
    "FU": ("fujairah", "الفجيرة", "الفجيره", "dibba", "دبا"),
}


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.model
    def _mizan_emirate_from_city(self, city, country):
        if not city or not country or country.code != "AE":
            return False
        text = city.strip().lower()
        for code, spellings in EMIRATE_BY_CITY.items():
            if any(spelling in text for spelling in spellings):
                return self.env["res.country.state"].search([
                    ("country_id", "=", country.id), ("code", "=", code),
                ], limit=1)
        return False

    def _mizan_apply_emirate(self):
        """Fill the emirate where it is empty and the city names one."""
        for partner in self:
            if partner.state_id:
                continue
            state = self._mizan_emirate_from_city(
                partner.city, partner.country_id)
            if state:
                partner.state_id = state.id

    @api.model_create_multi
    def create(self, vals_list):
        partners = super().create(vals_list)
        partners._mizan_apply_emirate()
        return partners

    def write(self, vals):
        result = super().write(vals)
        if "city" in vals or "country_id" in vals:
            self._mizan_apply_emirate()
        return result

    @api.onchange("city", "country_id")
    def _mizan_onchange_city_emirate(self):
        """So the user sees the emirate appear as they type the city."""
        if self.country_id and self.country_id.code == "AE" and not self.state_id:
            state = self._mizan_emirate_from_city(self.city, self.country_id)
            if state:
                self.state_id = state
