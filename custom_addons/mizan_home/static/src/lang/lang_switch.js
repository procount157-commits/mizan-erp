/** @odoo-module **/
import { Component } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { user } from "@web/core/user";
import { browser } from "@web/core/browser/browser";

/** One tap from Arabic to English and back, instead of a trip to Preferences. */
export class MizanLangSwitch extends Component {
    static template = "mizan_home.LangSwitch";
    static props = {};

    setup() {
        this.orm = useService("orm");
    }

    get isArabic() {
        return (user.context.lang || "").startsWith("ar");
    }

    async toggle() {
        await this.orm.call("res.users", "mizan_switch_lang", []);
        browser.location.reload();
    }
}

registry.category("systray").add("mizan_home.lang_switch", { Component: MizanLangSwitch }, { sequence: 5 });
