# -*- coding: utf-8 -*-
from odoo import api, models, fields


class ProjectTaskExtend(models.Model):
    _inherit = 'project.task'

    work_order_ids = fields.One2many(
        'contractor.work.order', 'task_id',
        string='أوامر العمل')

    work_order_count = fields.Integer(
        compute='_compute_work_order_count',
        string='أوامر العمل')

    def write(self, vals):
        res = super().write(vals)
        # اعتماد المهام يغيّر نسبة الإنجاز للمسجد
        if {'review_state', 'stage_id', 'parent_id'} & set(vals):
            self._mosques()._refresh_work_progress()
        return res

    @api.model_create_multi
    def create(self, vals_list):
        tasks = super().create(vals_list)
        tasks._mosques()._refresh_work_progress()
        return tasks

    def _mosques(self):
        projects = self.mapped('project_id')
        if not projects or 'project_id' not in self.env['mosque.mosque']._fields:
            return self.env['mosque.mosque']
        return self.env['mosque.mosque'].sudo().search([('project_id', 'in', projects.ids)])

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
