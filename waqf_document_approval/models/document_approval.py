# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class DocumentApproval(models.Model):
    _name = 'waqf.document.approval'
    _description = 'طلب اعتماد وثيقة/مخطط'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(
        string='رقم الطلب', required=True, copy=False,
        readonly=True, default=lambda s: _('جديد'))
    title = fields.Char(string='عنوان الطلب', required=True, tracking=True)

    mosque_id = fields.Many2one(
        'mosque.mosque', string='المسجد', required=True,
        ondelete='restrict', tracking=True)
    work_order_id = fields.Many2one(
        'contractor.work.order', string='أمر العمل المرتبط',
        ondelete='set null')

    doc_type_id = fields.Many2one(
        'waqf.document.type', string='نوع الوثيقة',
        required=True, tracking=True)

    submitted_by = fields.Many2one(
        'res.users', string='مقدّم الطلب',
        default=lambda s: s.env.user, readonly=True)
    contractor_id = fields.Many2one(
        'res.partner', string='المقاول',
        compute='_compute_contractor', store=True)

    reviewed_by = fields.Many2one(
        'res.users', string='روجع بواسطة', readonly=True, tracking=True)
    review_date = fields.Datetime(string='تاريخ المراجعة', readonly=True)

    description = fields.Text(string='وصف / ملاحظات المقدّم')
    review_notes = fields.Text(string='ملاحظات الاستشاري', tracking=True)
    reject_reason = fields.Text(string='سبب الرفض')

    revision = fields.Integer(string='رقم المراجعة', default=0, tracking=True)

    state = fields.Selection([
        ('draft',     'مسودة — قيد رفع الملفات'),
        ('submitted', 'مُرسل — بانتظار الاعتماد'),
        ('approved',  'معتمد'),
        ('approved_comments', 'معتمد مع ملاحظات'),
        ('rejected',  'مرفوض — يلزم إعادة'),
    ], string='الحالة', default='draft', tracking=True, index=True)

    file_ids = fields.One2many(
        'waqf.document.approval.file', 'approval_id', string='الملفات')
    file_count = fields.Integer(
        string='عدد الملفات', compute='_compute_file_count', store=True)
    total_size = fields.Float(
        string='الحجم الكلي (MB)', compute='_compute_file_count', store=True)

    active = fields.Boolean(default=True)

    @api.depends('submitted_by')
    def _compute_contractor(self):
        for rec in self:
            rec.contractor_id = rec.submitted_by.partner_id

    @api.depends('file_ids', 'file_ids.file_size')
    def _compute_file_count(self):
        for rec in self:
            rec.file_count = len(rec.file_ids)
            rec.total_size = sum(rec.file_ids.mapped('file_size')) / (1024 * 1024)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('جديد')) == _('جديد'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'waqf.document.approval') or _('جديد')
        return super().create(vals_list)

    def action_submit(self):
        for rec in self:
            if not rec.file_ids:
                raise UserError(_('يجب رفع ملف واحد على الأقل قبل الإرسال.'))
            rec.write({'state': 'submitted'})
            rec.message_post(
                body=_('تم إرسال الطلب للاعتماد — %d ملف') % rec.file_count,
                subtype_xmlid='mail.mt_comment')

    def action_approve(self):
        for rec in self:
            rec.write({
                'state': 'approved',
                'reviewed_by': self.env.user.id,
                'review_date': fields.Datetime.now(),
            })
            rec.message_post(body=_('✅ تم اعتماد الوثائق'))

    def action_approve_comments(self):
        for rec in self:
            if not rec.review_notes:
                raise UserError(_('يرجى كتابة الملاحظات أولاً.'))
            rec.write({
                'state': 'approved_comments',
                'reviewed_by': self.env.user.id,
                'review_date': fields.Datetime.now(),
            })
            rec.message_post(
                body=_('✅ معتمد مع ملاحظات: %s') % rec.review_notes)

    def action_reject(self):
        for rec in self:
            if not rec.reject_reason:
                raise UserError(_('يرجى كتابة سبب الرفض.'))
            rec.write({
                'state': 'rejected',
                'reviewed_by': self.env.user.id,
                'review_date': fields.Datetime.now(),
            })
            rec.message_post(body=_('❌ مرفوض: %s') % rec.reject_reason)

    def action_resubmit(self):
        for rec in self:
            rec.write({
                'state': 'draft',
                'revision': rec.revision + 1,
                'reject_reason': False,
            })
            rec.message_post(
                body=_('تم فتح الطلب لإعادة الرفع (مراجعة %d)') % rec.revision)

    def action_reset_draft(self):
        self.write({'state': 'draft'})
