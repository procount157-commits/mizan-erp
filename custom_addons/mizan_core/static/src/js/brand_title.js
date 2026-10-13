/** @odoo-module **/
// The browser tab says "مقياس", not "Odoo": the title service's last part is
// the product name, and a client sees it on every tab they open.
import { registry } from "@web/core/registry";

registry.category("services").add("mizan_brand_title", {
    dependencies: ["title"],
    start(env, { title }) {
        title.setParts({ zopenerp: "مقياس" });
    },
});
