# -*- coding: utf-8 -*-
"""Arabic wording for the invoice email Odoo sends.

Odoo registers its mail templates with noupdate set, so a data file in another
module cannot change them — the record is skipped silently and the client keeps
emailing Arabic tax invoices under an English covering note. Writing the values
from a hook is the only way to land them.
"""

SUBJECT = (
    "{{ object.company_id.name }} — "
    "{{ 'فاتورة ضريبية' if object.move_type == 'out_invoice' else 'إشعار دائن' }} "
    "{{ object.name or '' }}"
)

BODY = """
<div style="margin:0px;padding:0px;font-size:14px;">
    <p style="margin:0 0 16px 0;">
        السادة <t t-out="object.partner_id.name or ''">العميل</t> المحترمون،
    </p>
    <p style="margin:0 0 16px 0;">
        نرفق لكم
        <t t-if="object.move_type == 'out_refund'">إشعاراً دائناً</t>
        <t t-else="">فاتورة ضريبية</t>
        رقم <strong t-out="object.name or ''">INV/0001</strong>
        بمبلغ <strong t-out="format_amount(object.amount_total, object.currency_id) or ''">0.00</strong>.
    </p>
    <p t-if="object.invoice_date_due and object.move_type == 'out_invoice'" style="margin:0 0 16px 0;">
        تاريخ الاستحقاق: <strong t-out="format_date(object.invoice_date_due) or ''">التاريخ</strong>.
    </p>
    <p style="margin:0 0 16px 0;">لأي استفسار يسعدنا تواصلكم معنا.</p>
    <p style="margin:0;">
        <t t-out="object.company_id.name or ''">الشركة</t><br/>
        <t t-if="object.company_id.vat">الرقم الضريبي: <t t-out="object.company_id.vat"/><br/></t>
        <t t-if="object.company_id.phone">هاتف: <t t-out="object.company_id.phone"/><br/></t>
        <t t-if="object.company_id.email"><t t-out="object.company_id.email"/></t>
    </p>
</div>
"""


def post_init_hook(env):
    template = env.ref("account.email_template_edi_invoice", raise_if_not_found=False)
    if template:
        template.write({"subject": SUBJECT, "body_html": BODY})
