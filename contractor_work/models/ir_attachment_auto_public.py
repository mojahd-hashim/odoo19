# -*- coding: utf-8 -*-
# models/ir_attachment_auto_public.py
# ضعه في أي مديول محمّل (مثل waqf_contractor_portal)
# وأضفه في models/__init__.py:
#   from . import ir_attachment_auto_public

from odoo import models, api

# النماذج التي مرفقاتها عامة تلقائياً للبوابة
PUBLIC_MODELS = [
    'contractor.work.order',
    'contractor.material.submittal',
    'contractor.qualification',
    'waqf.document.approval',
    'waqf.document.approval.file',
]


class IrAttachment(models.Model):
    _inherit = 'ir.attachment'

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('res_model') in PUBLIC_MODELS:
                vals['public'] = True
        return super().create(vals_list)

    def write(self, vals):
        # إذا نُقل المرفق لنموذج بوابة — اجعله عام
        if vals.get('res_model') in PUBLIC_MODELS:
            vals['public'] = True
        return super().write(vals)
