/** @odoo-module **/
// The Contracting app opens on its projects, one icon each, like the app
// grid; an icon opens the project with everything it owns, read from the
// ledger, and every entry screen one tap away. The server builds the
// figures and the actions (models/dashboard.py); this only draws them.
import { Component, onMounted, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class MizanProjectGrid extends Component {
    static template = "mizan_project_accounts.ProjectGrid";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, failed: false, query: "" });
        onMounted(() => this.load());
    }

    async load() {
        try {
            this.state.data = await this.orm.call("mizan.contract", "get_project_grid", []);
        } catch (e) {
            this.state.failed = true;
            console.error(e);
        }
    }

    get projects() {
        const q = this.state.query.trim().toLowerCase();
        const all = this.state.data?.projects || [];
        return q ? all.filter((p) => `${p.name} ${p.code} ${p.client}`.toLowerCase().includes(q)) : all;
    }

    open(project) {
        this.action.doAction({
            type: "ir.actions.client", tag: "mizan_project_dashboard",
            name: project.name, params: { contract_id: project.id },
        });
    }

    create() {
        this.action.doAction("mizan_project_accounts.action_project_new", {
            onClose: () => this.load(),
        });
    }
}

export class MizanProjectDashboard extends Component {
    static template = "mizan_project_accounts.ProjectDashboard";
    static props = { "*": true };

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.state = useState({ data: null, failed: false });
        onMounted(() => this.load());
    }

    get contractId() {
        return this.props.action?.params?.contract_id || this.props.action?.context?.active_id;
    }

    async load() {
        try {
            this.state.data = await this.orm.call("mizan.contract", "get_project_dashboard", [[this.contractId]]);
            this.state.failed = false;
        } catch (e) {
            this.state.failed = true;
            console.error(e);
        }
    }

    async run(action) {
        if (!action) {
            return;
        }
        await this.action.doAction(action, { onClose: () => this.load() });
    }
}

registry.category("actions").add("mizan_project_grid", MizanProjectGrid);
registry.category("actions").add("mizan_project_dashboard", MizanProjectDashboard);
