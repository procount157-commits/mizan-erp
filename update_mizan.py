import odoo
from odoo import api, SUPERUSER_ID

def run():
    # Search and update menu names directly in database
    menus = env['ir.ui.menu'].search([])
    for m in menus:
        if m.name and 'الميزان' in m.name:
            m.write({'name': 'Mizan ERP Enterprise'})
            print(f"Updated Menu ID {m.id} -> Mizan ERP Enterprise")

    # Upgrade custom module
    mod = env['ir.module.module'].search([('name', '=', 'mizan_core')])
    if mod:
        mod.button_immediate_upgrade()
        print("Module mizan_core upgraded successfully!")

    env.cr.commit()

run()
