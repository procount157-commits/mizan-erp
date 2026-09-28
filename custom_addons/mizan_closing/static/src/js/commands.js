/**
 * The month-end close in the command palette.
 *
 * Registered by this module rather than by the hub, so a database without it
 * is never offered a screen it does not have. A palette entry that errors is
 * worse than one that is missing: the first looks like a broken product.
 */
import { registry } from "@web/core/registry";
import { _t } from "@web/core/l10n/translation";

registry.category("command_provider").add("mizan_closing.close", {
    provide(env) {
        return [
            {
                name: _t("Month-End Close"),
                category: "mizan",
                action: () =>
                    env.services.action.doAction("mizan_closing.action_month_close"),
                props: { iconClass: "fa fa-lock" },
            },
        ];
    },
});
