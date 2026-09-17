/** @odoo-module **/

import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { DropdownItem } from "@web/core/dropdown/dropdown_item";
import { _t } from "@web/core/l10n/translation";

// The documents people create all day sit three clicks deep in their own apps.
// Each entry opens a blank form directly rather than the list it lives in.
const ENTRIES = [
    {
        label: _t("Customer Invoice"),
        icon: "fa-file-text-o",
        model: "account.move",
        context: { default_move_type: "out_invoice" },
    },
    {
        label: _t("Vendor Bill"),
        icon: "fa-file-text",
        model: "account.move",
        context: { default_move_type: "in_invoice" },
    },
    {
        label: _t("Payment"),
        icon: "fa-money",
        model: "account.payment",
        context: {},
    },
    {
        label: _t("Customer"),
        icon: "fa-user-plus",
        model: "res.partner",
        context: { default_customer_rank: 1 },
    },
    {
        label: _t("Expense"),
        icon: "fa-credit-card",
        model: "hr.expense",
        context: {},
    },
];

export class MizanQuickCreate extends Component {
    static template = "mizan_core.QuickCreate";
    static components = { Dropdown, DropdownItem };
    static props = {};

    setup() {
        this.action = useService("action");
        this.entries = ENTRIES;
    }

    onSelect(entry) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: entry.label,
            res_model: entry.model,
            views: [[false, "form"]],
            target: "current",
            context: entry.context,
        });
    }
}

registry
    .category("systray")
    .add("mizan_core.quick_create", { Component: MizanQuickCreate }, { sequence: 1 });
