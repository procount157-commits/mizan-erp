/** @odoo-module **/
// The home page. The server decides what it shows (models/home.py); this
// only draws it and opens what is tapped.
import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class MizanHome extends Component {
    static template = "mizan_home.Home";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, query: "", busy: false, failed: false });
        // Drawn first, filled after: waiting in onWillStart left the whole
        // screen blank for as long as the figures took on a slow phone.
        onMounted(() => this.load());
    }

    async load() {
        try {
            this.state.data = await this.orm.call("mizan.home", "get_home", []);
            this.state.failed = false;
        } catch (e) {
            this.state.failed = true;
            console.error(e);
        }
    }

    async open(link) {
        if (!link || this.state.busy) {
            return;
        }
        this.state.busy = true;
        try {
            const action = await this.orm.call("mizan.home", "resolve_link", [link]);
            if (action) {
                await this.action.doAction(action);
            }
        } finally {
            this.state.busy = false;
        }
    }

    async search(ev) {
        ev.preventDefault();
        const q = this.state.query.trim();
        if (!q) {
            return;
        }
        const action = await this.orm.call("mizan.home", "search", [q]);
        if (action) {
            await this.action.doAction(action, { onClose: () => this.load() });
        }
    }

    get placeholder() {
        return _t("Find an invoice, a cheque, a customer, a project…");
    }
}

registry.category("actions").add("mizan_home", MizanHome);
