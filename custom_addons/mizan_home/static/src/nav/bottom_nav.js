/** @odoo-module **/
// The phone's bottom bar: the places a person goes all day, by role, and a
// camera for whoever photographs receipts. Drawn only on small screens; on a
// computer the top bar does the job.
import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { _t } from "@web/core/l10n/translation";

// In order of preference: the first four the person can open are shown.
const APPS = [
    { xmlid: "mizan_owner.menu_owner_root", icon: "fa-building-o", label: _t("Owner") },
    { xmlid: "mizan_home.menu_home_root", icon: "fa-home", label: _t("Home") },
    { xmlid: "mizan_pettycash.menu_petty_root", icon: "fa-money", label: _t("Petty cash") },
    { xmlid: "mizan_ops.menu_ops_root", icon: "fa-tasks", label: _t("Operations") },
    { xmlid: "mizan_hub.menu_hub_root", icon: "fa-briefcase", label: _t("My work") },
    { xmlid: "mail.menu_root_discuss", icon: "fa-comments-o", label: _t("Chat") },
];

export class MizanBottomNav extends Component {
    static template = "mizan_home.BottomNav";
    static props = {};

    setup() {
        this.menu = useService("menu");
        this.action = useService("action");
        this.ui = useState(useService("ui"));
        this.state = useState({ camera: false });
        onWillStart(async () => {
            this.state.camera = await user.hasGroup("mizan_site.group_site_engineer");
        });
    }

    get items() {
        const byXmlid = Object.fromEntries(this.menu.getApps().map((app) => [app.xmlid, app]));
        return APPS.filter((a) => byXmlid[a.xmlid])
            .slice(0, 4)
            .map((a) => ({ ...a, menu: byXmlid[a.xmlid] }));
    }

    get current() {
        return this.menu.getCurrentApp()?.xmlid;
    }

    open(item) {
        this.menu.selectMenu(item.menu);
    }

    /** The rest of the apps: the same grid the top-right button opens. */
    more() {
        document.querySelector(".o_navbar_apps_menu button")?.click();
    }

    camera() {
        this.action.doAction("mizan_pettycash.action_capture_cash");
    }
}

registry.category("main_components").add("mizan_home.BottomNav", { Component: MizanBottomNav });
