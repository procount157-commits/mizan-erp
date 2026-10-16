/** @odoo-module **/
// The owner's page: drawn at once, filled from mizan.owner.get_summary().
import { Component, onMounted, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MizanOwner extends Component {
    static template = "mizan_owner.Page";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, failed: false });
        onMounted(() => {
            this.load();
            // Live enough for an owner: refreshed every two minutes while open.
            this.timer = setInterval(() => this.load(), 120000);
        });
        onWillUnmount(() => clearInterval(this.timer));
    }

    async load() {
        try {
            this.state.data = await this.orm.call("mizan.owner", "get_summary", []);
            this.state.failed = false;
        } catch (e) {
            this.state.failed = true;
            console.error(e);
        }
    }

    async open(action) {
        if (action) {
            await this.action.doAction(action);
        }
    }
}

registry.category("actions").add("mizan_owner", MizanOwner);
