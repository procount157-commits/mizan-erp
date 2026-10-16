# -*- coding: utf-8 -*-
import datetime

from odoo import fields


def plain_domain(domain):
    """A domain as text that literal_eval can read back.

    Screens here store the filter behind a figure as a string and rebuild the
    action from it. A date in that filter would be written as
    datetime.date(2026, 9, 30), which literal_eval refuses, and the screen
    would crash on open. As ISO text the ORM compares it exactly the same."""
    def plain(value):
        if isinstance(value, datetime.datetime):
            return fields.Datetime.to_string(value)
        if isinstance(value, datetime.date):
            return fields.Date.to_string(value)
        if isinstance(value, (list, tuple)):
            return type(value)(plain(v) for v in value)
        return value
    return repr([plain(leaf) for leaf in (domain or [])])
