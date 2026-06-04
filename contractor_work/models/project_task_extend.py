# -*- coding: utf-8 -*-
from odoo import models, fields


class ProjectTaskExtend(models.Model):
    _inherit = 'project.task'

    work_order_ids = fields.One2many(
        'contractor.work.order', 'task_id',
        string='أوامر العمل')

    work_order_count = fields.Integer(
        compute='_compute_work_order_count',
        string='أوامر العمل')

    def _compute_work_order_count(self):
        for rec in self:
            rec.work_order_count = len(rec.work_order_ids)

    def action_view_work_orders(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      f'أوامر عمل — {self.name}',
            'res_model': 'contractor.work.order',
            'view_mode': 'list,form',
            'domain':    [('task_id', '=', self.id)],
            'context':   {'default_task_id': self.id,
                          'default_mosque_id': self.project_id.mosque_id.id
                                              if self.project_id else False},
        }
