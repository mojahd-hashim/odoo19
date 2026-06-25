# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ContractorMaterialSubmittal(models.Model):
    """عينات المواد — مطلوبة لبعض بنود BOQ."""
    _name        = 'contractor.material.submittal'
    _description = 'عينة مادة'
    _inherit     = ['mail.thread']
    _order       = 'date_submitted desc'

    name = fields.Char(
        string='رقم العينة', readonly=True,
        copy=False, default='جديد')

    work_order_id = fields.Many2one(
        'contractor.work.order', string='أمر العمل',
        ondelete='cascade')

    mosque_id = fields.Many2one(
        'mosque.mosque', string='المسجد')

    boq_id = fields.Many2one(
        'mosque.boq', string='البند المرتبط',
        required=True)

    material_name   = fields.Char(string='اسم المادة', required=True)
    manufacturer    = fields.Char(string='المصنع / المورد')
    model_number    = fields.Char(string='رقم الموديل')
    specifications  = fields.Text(string='المواصفات الفنية')

    date_submitted  = fields.Date(string='تاريخ التقديم', default=fields.Date.today)

    document_ids = fields.Many2many(
        'ir.attachment',
        'submittal_docs_rel', 'sub_id', 'att_id',
        string='الوثائق والصور')

    state = fields.Selection([
        ('draft',    'مسودة'),
        ('submitted','بانتظار المراجعة'),
        ('approved', 'معتمد ✅'),
        ('rejected', 'مرفوض'),
    ], string='الحالة', default='draft', tracking=True)

    approved_by    = fields.Many2one('res.users', string='اعتمد بواسطة', readonly=True)
    approval_date  = fields.Date(string='تاريخ الاعتماد', readonly=True)
    reject_reason  = fields.Text(string='سبب الرفض')
    notes          = fields.Text(string='ملاحظات المستشار')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'جديد') == 'جديد':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'contractor.material.submittal') or 'جديد'
        return super().create(vals_list)

    def action_submit(self):
        if not self.document_ids:
            raise UserError('يجب رفع وثيقة أو صورة واحدة على الأقل.')
        self.write({'state': 'submitted'})
        self.message_post(body='📋 تم إرسال العينة للمراجعة')

    def action_approve(self):
        self.write({
            'state':        'approved',
            'approved_by':  self.env.user.id,
            'approval_date': fields.Date.today(),
        })
        self.message_post(body=f'✅ اعتمدت العينة: {self.env.user.name}')

    def action_reject(self):
        self.write({'state': 'rejected'})
        self.message_post(body=f'❌ رُفضت العينة: {self.reject_reason or ""}')
