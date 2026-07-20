# -*- coding: utf-8 -*-
from odoo import models, fields, api


class PaymentClaimLine(models.Model):
    _name = 'waqf.payment.claim.line'
    _description = 'بند مستخلص مالي'
    _order = 'sequence, id'

    claim_id = fields.Many2one('waqf.payment.claim', string='المستخلص',
                                required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='ترتيب', default=10)

    # ── ربط بالبند والعمل ──────────────────────────────────
    work_order_id = fields.Many2one('contractor.work.order', string='أمر العمل')
    boq_item_code = fields.Char(string='رمز البند')
    description   = fields.Char(string='وصف العمل', required=True)
    uom           = fields.Char(string='الوحدة')

    # ── الكميات ────────────────────────────────────────────
    contract_qty   = fields.Float(string='كمية العقد', digits=(16, 3))
    unit_price     = fields.Float(string='سعر الوحدة', digits=(16, 2))
    contract_value = fields.Monetary(string='قيمة العقد',
                                      compute='_compute_values', store=True,
                                      currency_field='currency_id')

    previous_qty    = fields.Float(string='كمية سابقة', digits=(16, 3))
    previous_amount = fields.Monetary(string='مبلغ سابق',
                                       compute='_compute_values', store=True,
                                       currency_field='currency_id')

    current_qty    = fields.Float(string='الكمية الحالية', digits=(16, 3))
    current_amount = fields.Monetary(string='المبلغ الحالي',
                                      compute='_compute_values', store=True,
                                      currency_field='currency_id')

    cumulative_qty = fields.Float(string='الكمية التراكمية',
                                   compute='_compute_values', store=True, digits=(16, 3))
    completion_pct = fields.Float(string='نسبة الإنجاز %',
                                   compute='_compute_values', store=True)

    currency_id = fields.Many2one(related='claim_id.currency_id')
    notes = fields.Char(string='ملاحظات')

    @api.depends('contract_qty', 'unit_price', 'previous_qty', 'current_qty')
    def _compute_values(self):
        for rec in self:
            rec.contract_value  = rec.contract_qty * rec.unit_price
            rec.previous_amount = rec.previous_qty * rec.unit_price
            rec.current_amount  = rec.current_qty * rec.unit_price
            rec.cumulative_qty  = rec.previous_qty + rec.current_qty
            if rec.contract_qty:
                rec.completion_pct = (rec.cumulative_qty / rec.contract_qty) * 100
            else:
                rec.completion_pct = 0
