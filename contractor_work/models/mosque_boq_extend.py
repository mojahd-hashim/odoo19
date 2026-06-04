# -*- coding: utf-8 -*-
from odoo import models, fields


class MosqueBOQExtend(models.Model):
    _inherit = 'mosque.boq'

    requires_sample = fields.Boolean(
        string='يتطلب عينة مادة',
        default=False,
        help='يجب اعتماد عينة قبل تسليم الأعمال')

    requires_qualification = fields.Boolean(
        string='يتطلب تأهيل مقاول',
        default=False,
        help='يجب أن يكون للمقاول تأهيل معتمد لهذا النوع')

    work_order_line_ids = fields.One2many(
        'contractor.work.order.boq', 'boq_id',
        string='بنود أوامر العمل')
