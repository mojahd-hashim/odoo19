# -*- coding: utf-8 -*-
import json
import requests
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class WaqfApiSync(models.AbstractModel):
    _name = 'waqf.api.sync'
    _description = 'مزامنة API مع نظام العقود'

    @api.model
    def send_claim(self, claim):
        """إرسال المستخلص المعتمد لنظام العقود (أودو آخر) عبر XML-RPC / REST."""
        ICP = self.env['ir.config_parameter'].sudo()

        url      = ICP.get_param('waqf.contracts.api_url', '')
        db       = ICP.get_param('waqf.contracts.api_db', '')
        login    = ICP.get_param('waqf.contracts.api_login', '')
        password = ICP.get_param('waqf.contracts.api_password', '')
        api_key  = ICP.get_param('waqf.contracts.api_key', '')

        if not url:
            raise UserError(_(
                'لم يتم تكوين رابط API نظام العقود.\n'
                'اذهب إلى: الإعدادات → معاملات → معاملات النظام\n'
                'وأضف: waqf.contracts.api_url'))

        # ── تحضير البيانات ────────────────────────────────
        payload = {
            'claim_ref':      claim.name,
            'mosque_code':    claim.mosque_id.code or '',
            'mosque_name':    claim.mosque_id.name,
            'contractor':     claim.contractor_id.name,
            'contractor_vat': claim.contractor_id.vat or '',
            'claim_type':     claim.claim_type,
            'claim_number':   claim.claim_number,
            'period_from':    str(claim.period_from),
            'period_to':      str(claim.period_to),
            'contract_value': claim.contract_value,
            'total_claimed':  claim.total_claimed,
            'total_previous': claim.total_previous,
            'total_current':  claim.total_current,
            'retention_pct':  claim.retention_pct,
            'retention_amt':  claim.retention_amount,
            'deductions':     claim.deductions or 0,
            'net_payable':    claim.net_payable,
            'completion_pct': claim.completion_pct,
            'approved_by':    claim.approved_by.name or '',
            'approved_date':  str(claim.approved_date or ''),
            'lines': [{
                'code':         l.boq_item_code or '',
                'description':  l.description,
                'uom':          l.uom or '',
                'contract_qty': l.contract_qty,
                'unit_price':   l.unit_price,
                'previous_qty': l.previous_qty,
                'current_qty':  l.current_qty,
                'current_amt':  l.current_amount,
            } for l in claim.line_ids],
        }

        # ── إرسال — REST API ──────────────────────────────
        headers = {'Content-Type': 'application/json'}
        if api_key:
            headers['Authorization'] = 'Bearer %s' % api_key

        try:
            resp = requests.post(
                '%s/api/payment-claim/receive' % url.rstrip('/'),
                data=json.dumps({'jsonrpc': '2.0', 'params': payload}),
                headers=headers,
                timeout=30,
            )
            resp.raise_for_status()
            result = resp.json().get('result', {})

            if result.get('error'):
                raise UserError(result['error'])

            return result

        except requests.exceptions.ConnectionError:
            raise UserError(_(
                'تعذّر الاتصال بنظام العقود على الرابط:\n%s\n'
                'تحقق من الرابط واتصال الشبكة.') % url)
        except requests.exceptions.Timeout:
            raise UserError(_('انتهت مهلة الاتصال بنظام العقود (30 ثانية).'))
        except Exception as e:
            raise UserError(_('خطأ في المزامنة: %s') % str(e))

    @api.model
    def receive_claim(self, **params):
        """نقطة استقبال في نظام العقود — تُنشئ فاتورة مورّد."""
        # هذه الدالة تُوضع في نظام العقود المستقبل
        # مثال على الاستقبال:
        #
        # invoice = self.env['account.move'].sudo().create({
        #     'move_type': 'in_invoice',
        #     'partner_id': contractor.id,
        #     'ref': params.get('claim_ref'),
        #     'invoice_line_ids': [(0, 0, {
        #         'name': line['description'],
        #         'quantity': line['current_qty'],
        #         'price_unit': line['unit_price'],
        #     }) for line in params.get('lines', [])],
        # })
        # return {'invoice_id': invoice.id, 'success': True}
        return {'invoice_id': 0, 'success': True, 'message': 'Placeholder'}
