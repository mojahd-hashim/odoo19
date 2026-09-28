# -*- coding: utf-8 -*-
from odoo import models

WO_ACCEPTED = ('graded', 'testing', 'warranty', 'closed')
WO_IN_PROGRESS = ('approved', 'delivered', 'rework', 'testing')


class MosqueWorkProgress(models.Model):
    """الإنجاز = متوسط نسبتين (بالعدد، لا بالكميات):
       • مهام الخطة المعتمدة من الاستشاري ÷ كل مهام الخطة
       • أوامر العمل المقبولة (A/B) ÷ أوامر العمل المرفوعة (عدا المسودة والمرفوضة)"""
    _inherit = 'mosque.mosque'

    def _work_progress_parts(self):
        self.ensure_one()
        if not isinstance(self.id, int):
            return {}
        env = self.env
        parts = {}

        # ── أوامر العمل ────────────────────────────────────
        wos = env['contractor.work.order'].sudo().search(
            [('mosque_id', '=', self.id), ('state', 'not in', ['draft', 'rejected'])])
        done = wos.filtered(lambda w: w.grade in ('a', 'b') and w.state in WO_ACCEPTED)
        parts.update(
            wo_total=len(wos), wo_done=len(done),
            wo_inprogress=len(wos.filtered(lambda w: w.state in WO_IN_PROGRESS and not w.boq_executed_posted)),
            wo_pct=round(len(done) / len(wos) * 100, 1) if wos else None,
        )

        # ── مهام خطة المشروع (المهام الطرفية، بدون قوالب المهام الدورية) ──
        project = self.project_id if 'project_id' in self._fields else False
        if project:
            Task = env['project.task'].sudo()
            tasks = Task.search([('project_id', '=', project.id), ('child_ids', '=', False)]).filtered(
                lambda t: '(Template)' not in (t.name or ''))
            if 'review_state' in Task._fields:
                approved = tasks.filtered(lambda t: t.review_state == 'approved')
            else:
                approved = tasks.filtered(lambda t: t.stage_id.fold)
            parts.update(
                task_total=len(tasks), task_done=len(approved),
                tasks_pct=round(len(approved) / len(tasks) * 100, 1) if tasks else None,
            )
        return parts

    def _refresh_work_progress(self):
        """يُعلِم الحقول المحسوبة بالتغيير لتُحدَّث في نهاية العملية."""
        mosques = self.filtered(lambda m: isinstance(m.id, int))
        if mosques:
            mosques.modified(['planned_start'])
