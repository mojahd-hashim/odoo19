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

    # ── بيانات أساسية ──────────────────────────────────────
    claim_type = fields.Selection([
        ('progress',  'مستخلص جاري'),
        ('final',     'مستخلص ختامي'),
        ('variation', 'أمر تغيير'),
        ('retention', 'إفراج ضمان'),
    ], string='نوع المستخلص', default='progress', required=True, tracking=True)

    payment_number = fields.Integer(string='رقم الدفعة التسلسلي', default=1, tracking=True)

    period_from = fields.Date(string='من تاريخ', required=True)
    period_to   = fields.Date(string='إلى تاريخ', required=True)

    # ── بيان الاستشاري ─────────────────────────────────────
    currency_id = fields.Many2one('res.currency', string='العملة',
                                   default=lambda s: s.env.company.currency_id)
    amount = fields.Monetary(string='المبلغ المطالب به',
                              required=True, currency_field='currency_id', tracking=True)
    description = fields.Text(string='بيان الاستشاري', required=True,
                               help='وصف الأعمال المنجزة والمبررات')

    retention_pct = fields.Float(string='نسبة الضمان %', default=10.0)
    retention_amount = fields.Monetary(string='محتجز الضمان',
                                        compute='_compute_net', store=True,
                                        currency_field='currency_id')
    deductions = fields.Monetary(string='خصومات أخرى', currency_field='currency_id')
    net_payable = fields.Monetary(string='صافي المستحق',
                                   compute='_compute_net', store=True,
                                   currency_field='currency_id')

    # ── المستندات ──────────────────────────────────────────
    attachment_ids = fields.Many2many('ir.attachment', 'payment_claim_att_rel',
                                      'claim_id', 'att_id', string='المستندات الداعمة')

    # ── دورة الاعتماد ─────────────────────────────────────
    state = fields.Selection([
        ('draft',      'مسودة'),
        ('submitted',  'مقدّم من الاستشاري'),
        ('reviewed',   'راجعه مهندس الوقف'),
        ('approved',   'معتمد من المدير'),
        ('synced',     'مُرسل لنظام الدفعات'),
        ('rejected',   'مرفوض'),
    ], string='الحالة', default='draft', tracking=True, index=True)

    submitted_by   = fields.Many2one('res.users', string='الاستشاري', readonly=True)
    submitted_date = fields.Datetime(string='تاريخ التقديم', readonly=True)
    reviewed_by    = fields.Many2one('res.users', string='مهندس الوقف', readonly=True)
    reviewed_date  = fields.Datetime(string='تاريخ المراجعة', readonly=True)
    review_notes   = fields.Text(string='ملاحظات مهندس الوقف', tracking=True)
    approved_by    = fields.Many2one('res.users', string='المدير المعتمد', readonly=True)
    approved_date  = fields.Datetime(string='تاريخ الاعتماد', readonly=True)
    approval_notes = fields.Text(string='ملاحظات المدير', tracking=True)
    reject_reason  = fields.Text(string='سبب الرفض')

    # ── ربط نظام الدفعات (Odoo 15) ────────────────────────
    external_installment_id = fields.Integer(
        string='رقم القسط في نظام الدفعات', readonly=True, copy=False)
    sync_date  = fields.Datetime(string='تاريخ المزامنة', readonly=True)
    sync_error = fields.Text(string='خطأ المزامنة', readonly=True)

    @api.depends('amount', 'retention_pct', 'deductions')
    def _compute_net(self):
        for rec in self:
            rec.retention_amount = rec.amount * (rec.retention_pct / 100)
            rec.net_payable = rec.amount - rec.retention_amount - (rec.deductions or 0)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'waqf.payment.claim') or _('جديد')
        return super().create(vals_list)

    def action_submit(self):
        for rec in self:
            if not rec.amount:
                raise UserError(_('يجب تحديد المبلغ.'))
            if not (rec.description or '').strip():
                raise UserError(_('يجب كتابة بيان الاستشاري.'))
            rec.write({
                'state': 'submitted',
                'submitted_by': self.env.user.id,
                'submitted_date': fields.Datetime.now(),
            })
            rec.message_post(body=_('📋 تم تقديم المستخلص — %s ريال')
                             % '{:,.2f}'.format(rec.amount))

    def action_review(self):
        for rec in self:
            rec.write({
                'state': 'reviewed',
                'reviewed_by': self.env.user.id,
                'reviewed_date': fields.Datetime.now(),
            })
            rec.message_post(body=_('✅ مهندس الوقف وافق%s')
                             % ('\n' + rec.review_notes if rec.review_notes else ''))

    def action_approve(self):
        for rec in self:
            rec.write({
                'state': 'approved',
                'approved_by': self.env.user.id,
                'approved_date': fields.Datetime.now(),
            })
            rec.message_post(body=_('✅ المدير اعتمد — صافي: %s ريال')
                             % '{:,.2f}'.format(rec.net_payable))

    def action_reject(self):
        for rec in self:
            if not (rec.reject_reason or '').strip():
                raise UserError(_('يرجى كتابة سبب الرفض.'))
            rec.write({'state': 'rejected'})
            rec.message_post(body=_('❌ مرفوض: %s') % rec.reject_reason)

    def action_reset_draft(self):
        self.write({
            'state': 'draft',
            'submitted_by': False, 'submitted_date': False,
            'reviewed_by': False, 'reviewed_date': False,
            'approved_by': False, 'approved_date': False,
            'reject_reason': False,
        })

    def action_sync_to_payments(self):
        for rec in self:
            if rec.state != 'approved':
                raise UserError(_('يجب اعتماد المستخلص أولاً.'))
            rec._sync_api()

    def _sync_api(self):
        self.ensure_one()
        try:
            result = self.env['waqf.api.sync'].send_installment(self)
            self.write({
                'state': 'synced',
                'external_installment_id': result.get('installment_id', 0),
                'sync_date': fields.Datetime.now(),
                'sync_error': False,
            })
            self.message_post(body=_('🔗 تم الإرسال — قسط رقم: %s')
                              % result.get('installment_id', '—'))
        except Exception as e:
            self.write({'sync_error': str(e)})
            self.message_post(body=_('⚠️ فشل: %s') % str(e))
