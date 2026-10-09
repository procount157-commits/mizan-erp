/**
 * Register Miqyas's own screens in the command palette.
 *
 * Odoo 18 already ships the palette, and Ctrl+K already finds menus by name.
 * What it does not do is put the handful of things a finance manager opens
 * twenty times a day above the fifty menus that happen to share a word with
 * them — and the daily screens are exactly the ones worth a keystroke.
 *
 * Deliberately a short list. A palette that offers everything is a menu with
 * a worse interface; its value is that the first result is the right one.
 */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

const COMMANDS = [
    {
        xmlid: "mizan_hub.action_find",
        name: _t("Find anything — across every document"),
        icon: "fa fa-search",
    },
    {
        xmlid: "mizan_hub.action_inbox_open",
        name: _t("Work Inbox — what is waiting for me"),
        icon: "fa fa-inbox",
    },
    {
        xmlid: "mizan_hub.action_dashboard",
        name: _t("Dashboard"),
        icon: "fa fa-tachometer",
    },
    {
        xmlid: "mizan_hub.action_health_open",
        name: _t("Project Health"),
        icon: "fa fa-heartbeat",
    },
    {
        xmlid: "mizan_hub.action_quality_open",
        name: _t("Data Quality"),
        icon: "fa fa-check-square-o",
    },
];

registry.category("command_provider").add("mizan_hub.screens", {
    async provide(env) {
        const commands = [];
        for (const entry of COMMANDS) {
            commands.push({
                name: entry.name,
                category: "mizan",
                // Resolved when the command is chosen, not when the
                // palette opens: looking up six actions on every keystroke to
                // decide what to offer is work nobody asked for.
                action: () => env.services.action.doAction(entry.xmlid),
                props: { iconClass: entry.icon },
            });
        }
        return commands;
    },
});

registry.category("command_categories").add(
    "mizan",
    { namespace: "default", name: _t("Miqyas") },
    { sequence: 5 }
);
