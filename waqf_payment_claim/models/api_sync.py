# -*- coding: utf-8 -*-
import xmlrpc.client
from odoo import models, api, _
from odoo.exceptions import UserError

CONTRACT_ID = 242


class WaqfApiSync(models.AbstractModel):
    _name = 'waqf.api.sync'
    _description = 'مزامنة مع نظام الدفعات (Odoo 15)'

    @api.model
    def _get_connection(self):
        ICP = self.env['ir.config_parameter'].sudo()
        url      = ICP.get_param('waqf.odoo15.url', '')
        db       = ICP.get_param('waqf.odoo15.db', '')
        login    = ICP.get_param('waqf.odoo15.login', '')
        password = ICP.get_param('waqf.odoo15.password', '')

        if not all([url, db, login, password]):
            raise UserError(_(
                'لم يتم تكوين اتصال Odoo 15.\n\n'
                'أضف في معاملات النظام:\n'
                '  waqf.odoo15.url\n  waqf.odoo15.db\n'
                '  waqf.odoo15.login\n  waqf.odoo15.password'))

        try:
            common = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/common' % url.rstrip('/'), allow_none=True)
            uid = common.authenticate(db, login, password, {})
            if not uid:
                raise UserError(_('فشل تسجيل الدخول في Odoo 15.'))
            models_proxy = xmlrpc.client.ServerProxy(
                '%s/xmlrpc/2/object' % url.rstrip('/'), allow_none=True)
            return db, uid, password, models_proxy
        except xmlrpc.client.Fault as e:
            raise UserError(_('خطأ Odoo 15: %s') % str(e))
        except ConnectionRefusedError:
            raise UserError(_('تعذّر الاتصال بـ Odoo 15 على: %s') % url)

    @api.model
    def send_installment(self, claim):
        db, uid, password, proxy = self._get_connection()

        type_labels = dict(claim._fields['claim_type'].selection)

        vals = {
            'contract_id': CONTRACT_ID,
            'name':        '%s — %s' % (claim.name, type_labels.get(claim.claim_type, '')),
            'amount':      claim.net_payable,
            'date_from':   str(claim.period_from),
            'date_to':     str(claim.period_to),
            'notes':       (claim.description or '') + '\n\n'
                           + 'نوع المستخلص: %s\n' % type_labels.get(claim.claim_type, '')
                           + 'رقم الدفعة: %d\n' % claim.payment_number
                           + 'المبلغ: {:,.2f}\n'.format(claim.amount)
                           + 'محتجز الضمان: {:,.2f}\n'.format(claim.retention_amount)
                           + 'خصومات: {:,.2f}\n'.format(claim.deductions or 0)
                           + 'صافي المستحق: {:,.2f}\n'.format(claim.net_payable)
                           + 'اعتمده: %s' % (claim.approved_by.name or ''),
            # 'budget_line_id': ...,  # يُحدد لاحقاً
        }

        try:
            installment_id = proxy.execute_kw(
                db, uid, password,
                'line.contract.installment', 'create', [vals])
            return {'installment_id': installment_id, 'success': True}
        except xmlrpc.client.Fault as e:
            raise UserError(_('خطأ Odoo 15: %s') % str(e))
