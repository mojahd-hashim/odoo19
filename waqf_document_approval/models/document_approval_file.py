# -*- coding: utf-8 -*-
from odoo import models, fields, api, _


class DocumentApprovalFile(models.Model):
    _name = 'waqf.document.approval.file'
    _description = 'ملف ضمن طلب اعتماد'
    _order = 'sequence, id'

    approval_id = fields.Many2one(
        'waqf.document.approval', string='الطلب',
        required=True, ondelete='cascade', index=True)
    sequence = fields.Integer(string='الترتيب', default=10)

    name = fields.Char(string='اسم الملف', required=True)

    # ── التخزين على القرص (filestore) وليس DB ──────────────
    # attachment=True يجعل Odoo يخزّن المحتوى في filestore على القرص
    attachment_id = fields.Many2one(
        'ir.attachment', string='المرفق', ondelete='cascade')

    file_data = fields.Binary(
        string='الملف', attachment=True,  # ← التخزين على القرص
        related='attachment_id.datas', readonly=False)
    file_size = fields.Integer(
        string='الحجم (بايت)', related='attachment_id.file_size', store=True)
    mimetype = fields.Char(
        related='attachment_id.mimetype', string='نوع الملف')

    file_size_human = fields.Char(
        string='الحجم', compute='_compute_size_human')

    note = fields.Char(string='ملاحظة على الملف')
    is_final = fields.Boolean(string='الملف الأخير', default=False)

    @api.depends('file_size')
    def _compute_size_human(self):
        for rec in self:
            size = rec.file_size or 0
            if size < 1024:
                rec.file_size_human = '%d B' % size
            elif size < 1024 * 1024:
                rec.file_size_human = '%.1f KB' % (size / 1024)
            else:
                rec.file_size_human = '%.1f MB' % (size / (1024 * 1024))

    def action_download(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%d?download=true' % self.attachment_id.id,
            'target': 'self',
        }


class DocumentType(models.Model):
    _name = 'waqf.document.type'
    _description = 'نوع الوثيقة'
    _order = 'name'

    name = fields.Char(string='الاسم', required=True, translate=True)
    code = fields.Char(string='الرمز')
    active = fields.Boolean(default=True)
