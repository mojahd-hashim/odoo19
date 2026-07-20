# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class PaymentClaim(models.Model):
    _name = 'waqf.payment.claim'
    _description = 'مستخلص مالي'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='رقم المستخلص', required=True, copy=False,
                       readonly=True, default=lambda s: _('جديد'))

    mosque_id = fields.Many2one('mosque.mosque', string='المسجد',
                                required=True, tracking=True, ondelete='restrict')
    contractor_id = fields.Many2one('res.partner', string='المقاول',
                                    required=True, tracking=True)

    claim_type = fields.Selection([
        ('progress',  'مستخلص جاري'),
        ('final',     'مستخلص ختامي'),
        ('variation', 'أمر تغيير'),
        ('retention', 'إفراج ضمان'),
    ], string='نوع المستخلص', default='progress', required=True, tracking=True)

    claim_number = fields.Integer(string='رقم الدفعة', default=1, tracking=True)

    period_from = fields.Date(string='من تاريخ', required=True)
    period_to   = fields.Date(string='إلى تاريخ', required=True)

    currency_id = fields.Many2one('res.currency', string='العملة',
                                   default=lambda s: s.env.company.currency_id)

    line_ids = fields.One2many('waqf.payment.claim.line', 'claim_id', string='بنود المستخلص')

    contract_value = fields.Monetary(string='قيمة العقد', currency_field='currency_id')

    total_claimed = fields.Monetary(string='إجمالي الأعمال المنجزة',
                                     compute='_compute_totals', store=True, currency_field='currency_id')
    total_previous = fields.Monetary(string='المستخلصات السابقة',
                                      compute='_compute_totals', store=True, currency_field='currency_id')
    total_current = fields.Monetary(string='المستخلص الحالي',
                                     compute='_compute_totals', store=True, currency_field='currency_id')

    retention_pct = fields.Float(string='نسبة الضمان %', default=10.0)
    retention_amount = fields.Monetary(string='محتجز الضمان',
                                        compute='_compute_totals', store=True, currency_field='currency_id')
    deductions = fields.Monetary(string='خصومات أخرى', currency_field='currency_id')
    net_payable = fields.Monetary(string='صافي المستحق',
                                   compute='_compute_totals', store=True, currency_field='currency_id')
    completion_pct = fields.Float(string='نسبة الإنجاز %',
                                   compute='_compute_totals', store=True)

    state = fields.Selection([
        ('draft',      'مسودة'),
        ('submitted',  'مقدّم من الاستشاري'),
        ('reviewed',   'راجعه مهندس الوقف'),
        ('approved',   'معتمد من المدير'),
        ('synced',     'مُرسل لنظام العقود'),
        ('rejected',   'مرفوض'),
    ], string='الحالة', default='draft', tracking=True, index=True)

    submitted_by = fields.Many2one('res.users', string='الاستشاري', readonly=True)
    submitted_date = fields.Datetime(string='تاريخ التقديم', readonly=True)
    reviewed_by = fields.Many2one('res.users', string='مهندس الوقف', readonly=True)
    reviewed_date = fields.Datetime(string='تاريخ المراجعة', readonly=True)
    review_notes = fields.Text(string='ملاحظات مهندس الوقف', tracking=True)
    approved_by = fields.Many2one('res.users', string='المدير المعتمد', readonly=True)
    approved_date = fields.Datetime(string='تاريخ الاعتماد', readonly=True)
    approval_notes = fields.Text(string='ملاحظات المدير', tracking=True)
    reject_reason = fields.Text(string='سبب الرفض')

    external_invoice_id = fields.Integer(string='رقم الفاتورة الخارجية', readonly=True, copy=False)
    sync_date = fields.Datetime(string='تاريخ المزامنة', readonly=True)
    sync_error = fields.Text(string='خطأ المزامنة', readonly=True)

    description = fields.Text(string='ملاحظات عامة')
    attachment_ids = fields.Many2many('ir.attachment', 'payment_claim_att_rel',
                                      'claim_id', 'att_id', string='المستندات الداعمة')

    @api.depends('line_ids.current_amount', 'line_ids.previous_amount',
                 'retention_pct', 'deductions', 'contract_value')
    def _compute_totals(self):
        for rec in self:
            rec.total_claimed  = sum(rec.line_ids.mapped('current_amount'))
            rec.total_previous = sum(rec.line_ids.mapped('previous_amount'))
            rec.total_current  = rec.total_claimed - rec.total_previous
            rec.retention_amount = rec.total_current * (rec.retention_pct / 100)
            rec.net_payable = rec.total_current - rec.retention_amount - (rec.deductions or 0)
            if rec.contract_value:
                rec.completion_pct = (rec.total_claimed / rec.contract_value) * 100
            else:
                rec.completion_pct = 0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'waqf.payment.claim') or _('جديد')
        return super().create(vals_list)

    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                raise UserError(_('يجب إضافة بند واحد على الأقل.'))
            rec.write({
                'state': 'submitted',
                'submitted_by': self.env.user.id,
                'submitted_date': fields.Datetime.now(),
            })
            rec.message_post(body=_('📋 تم تقديم المستخلص — المبلغ: %s ريال')
                             % '{:,.2f}'.format(rec.total_current))

    def action_review(self):
        for rec in self:
            rec.write({
                'state': 'reviewed',
                'reviewed_by': self.env.user.id,
                'reviewed_date': fields.Datetime.now(),
            })
            rec.message_post(body=_('✅ تمت المراجعة من مهندس الوقف%s')
                             % ('\n' + rec.review_notes if rec.review_notes else ''))

    def action_approve(self):
        for rec in self:
            rec.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })
            rec.message_post(body=_('✅ اعتمد المدير — صافي المستحق: %s ريال')
                             % '{:,.2f}'.format(rec.net_payable))

    def action_reject(self):
        for rec in self:
            if not (rec.reject_reason or '').strip():
                raise UserError(_('يرجى كتابة سبب الرفض.'))
            rec.write({'state': 'rejected'})
            rec.message_post(body=_('❌ مرفوض: %s') % rec.reject_reason)

    def action_reset_draft(self):
        self.write({
            'state': 'draft', 'submitted_by': False, 'submitted_date': False,
            'reviewed_by': False, 'reviewed_date': False,
            'approved_by': False, 'approved_date': False,
            'reject_reason': False,
        })

    def action_sync_to_contracts(self):
        for rec in self:
            if rec.state != 'approved':
                raise UserError(_('يجب اعتماد المستخلص أولاً.'))
            rec._sync_api()

    def _sync_api(self):
        self.ensure_one()
        try:
            result = self.env['waqf.api.sync'].send_claim(self)
            self.write({
                'state': 'synced',
                'external_invoice_id': result.get('invoice_id', 0),
                'sync_date': fields.Datetime.now(),
                'sync_error': False,
            })
            self.message_post(body=_('🔗 تم الإرسال لنظام العقود — فاتورة: %s')
                              % result.get('invoice_id', '—'))
        except Exception as e:
            self.write({'sync_error': str(e)})
            self.message_post(body=_('⚠️ فشل الإرسال: %s') % str(e))
