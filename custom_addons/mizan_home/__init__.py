from . import models


def post_init_hook(env):
    """Make the home page everybody's first screen.

    Users whose first screen is still the default app grid, or the dashboard
    this page absorbs, open here from now on. Anyone who chose another start
    screen keeps it."""
    home = env.ref("mizan_home.action_home", raise_if_not_found=False)
    if not home:
        return
    dashboard = env.ref("mizan_hub.action_dashboard", raise_if_not_found=False)
    keep_away = {dashboard.id} if dashboard else set()
    users = env["res.users"].search([("share", "=", False), ("active", "=", True)])
    for user in users:
        if not user.action_id or user.action_id.id in keep_away:
            user.action_id = home.id
