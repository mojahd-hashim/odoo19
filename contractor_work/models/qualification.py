# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ContractorQualification(models.Model):
    """تأهيل المقاول لأعمال متخصصة."""
    _name        = 'contractor.qualification'
    _description = 'تأهيل المقاول'
    _inherit     = ['mail.thread', 'mail.activity.mixin']
    _order       = 'date_requested desc'

    name = fields.Char(
        string='رقم التأهيل', readonly=True,
        copy=False, default='جديد')

    supervisor_id = fields.Many2one(
        'res.partner', string='المقاول / المشرف',
        required=True, tracking=True)

    work_category_id = fields.Many2one(
        'mosque.boq.category', string='نوع العمل',
        required=True,
        help='نوع العمل الذي يتقدم للتأهيل فيه')

    # نطاق التأهيل
    scope = fields.Selection([
        ('all',      'كل المساجد'),
        ('specific', 'مساجد محددة'),
    ], string='النطاق', default='all', required=True)

    mosque_ids = fields.Many2many(
        'mosque.mosque', string='المساجد المحددة',
        help='يُترك فارغاً للتأهيل العام')

    # الوثائق
    document_ids = fields.Many2many(
        'ir.attachment',
        'qualification_docs_rel', 'qual_id', 'att_id',
        string='الوثائق والشهادات')

    description   = fields.Text(string='وصف الكفاءة')
    date_requested= fields.Date(string='تاريخ الطلب', default=fields.Date.today)

    # مرحلة اعتماد المستشار
    state = fields.Selection([
        ('draft',            'مسودة'),
        ('submitted',        'بانتظار المستشار'),
        ('consultant_ok',    'اعتمد المستشار'),
        ('submitted_waqf',   'بانتظار الوقف'),
        ('approved',         'معتمد ✅'),
        ('rejected',         'مرفوض'),
    ], string='الحالة', default='draft', tracking=True)

    consultant_approved_by = fields.Many2one(
        'res.users', string='اعتمد (المستشار)', readonly=True)
    consultant_approval_date = fields.Date(readonly=True)

    waqf_approved_by = fields.Many2one(
        'res.users', string='اعتمد (الوقف)', readonly=True)
    waqf_approval_date = fields.Date(readonly=True)

    reject_reason = fields.Text(string='سبب الرفض')
    notes         = fields.Text(string='ملاحظات')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'جديد') == 'جديد':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'contractor.qualification') or 'جديد'
        return super().create(vals_list)

    def action_submit(self):
        self.write({'state': 'submitted'})
        self.message_post(body='📋 تم إرسال طلب التأهيل للمستشار')

    def action_consultant_approve(self):
        self.write({
            'state': 'consultant_ok',
            'consultant_approved_by':   self.env.user.id,
            'consultant_approval_date': fields.Date.today(),
        })
        self.message_post(body=f'✅ اعتمد المستشار: {self.env.user.name}')

    def action_submit_waqf(self):
        self.write({'state': 'submitted_waqf'})
        self.message_post(body='📋 تم إرسال للوقف للاعتماد النهائي')

    def action_waqf_approve(self):
        self.write({
            'state': 'approved',
            'waqf_approved_by':   self.env.user.id,
            'waqf_approval_date': fields.Date.today(),
        })
        self.message_post(body=f'✅ اعتمد الوقف: {self.env.user.name}')

    def action_reject(self):
        self.write({'state': 'rejected'})
        self.message_post(body=f'❌ مرفوض: {self.reject_reason or ""}')

    def check_valid_for_mosque(self, mosque):
        """تحقق أن التأهيل ساري لمسجد معين."""
        self.ensure_one()
        if self.state != 'approved':
            return False
        if self.scope == 'all':
            return True
        return mosque in self.mosque_ids
