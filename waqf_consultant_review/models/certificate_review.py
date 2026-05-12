from odoo import models, fields, api, _
from odoo.exceptions import UserError


class MosqueCertificateReview(models.Model):
    """
    Extends mosque.certificate to enforce the green-tasks rule:
    Cannot submit to Waqf unless ALL project tasks are green (approved).
    """
    _inherit = 'mosque.certificate'

    # Summary fields for the form view
    tasks_total   = fields.Integer(compute='_compute_task_summary', string='Total Tasks')
    tasks_green   = fields.Integer(compute='_compute_task_summary', string='Green Tasks')
    tasks_not_green = fields.Integer(compute='_compute_task_summary', string='Not Green')
    all_tasks_green = fields.Boolean(compute='_compute_task_summary', string='All Green?')
    blocking_tasks_html = fields.Html(
        compute='_compute_task_summary',
        string='Blocking Tasks',
    )

    @api.depends('mosque_id', 'mosque_id.project_id')
    def _compute_task_summary(self):
        for cert in self:
            project = cert.mosque_id.project_id if cert.mosque_id else False
            if not project:
                cert.tasks_total         = 0
                cert.tasks_green         = 0
                cert.tasks_not_green     = 0
                cert.all_tasks_green     = True
                cert.blocking_tasks_html = ''
                continue

            # Only main tasks (not subtasks)
            main_tasks = self.env['project.task'].search([
                ('project_id', '=', project.id),
                ('parent_id',  '=', False),
            ])

            green     = main_tasks.filtered(
                lambda t: t.kanban_color == 'green')
            not_green = main_tasks.filtered(
                lambda t: t.kanban_color != 'green')

            cert.tasks_total     = len(main_tasks)
            cert.tasks_green     = len(green)
            cert.tasks_not_green = len(not_green)
            cert.all_tasks_green = len(not_green) == 0

            if not_green:
                color_labels = {
                    'grey':   ('⚪', 'لم تُعتمد — subtasks غير مكتملة'),
                    'red':    ('🔴', 'مرفوضة — subtask مرفوض'),
                    'yellow': ('🟡', 'مجمّدة — CO معلق'),
                    'orange': ('🟠', 'متأخرة'),
                }
                lines = []
                for t in not_green:
                    icon, label = color_labels.get(
                        t.kanban_color, ('⚪', t.kanban_color))
                    # Show subtask breakdown
                    sub_info = ''
                    if t.child_ids:
                        not_approved = t.child_ids.filtered(
                            lambda s: s.review_state != 'approved')
                        if not_approved:
                            sub_info = ' (%d/%d معتمدة)' % (
                                len(t.child_ids) - len(not_approved),
                                len(t.child_ids))
                    lines.append(
                        '<li>%s <b>%s</b>%s — %s</li>'
                        % (icon, t.name, sub_info, label))
                cert.blocking_tasks_html = (
                    '<ul style="margin:4px 0;padding-right:16px">%s</ul>'
                    % ''.join(lines))
            else:
                cert.blocking_tasks_html = ''

    # ── Override submit_to_waqf — enforce green rule ──────────────
    def action_submit_to_waqf(self):
        for cert in self:
            if not cert.all_tasks_green:
                not_green_names = []
                project = cert.mosque_id.project_id
                if project:
                    tasks = self.env['project.task'].search([
                        ('project_id', '=', project.id),
                        ('parent_id',  '=', False),
                        ('stage_id.is_closed', '=', False),
                    ])
                    not_green_names = [
                        t.name for t in tasks
                        if t.kanban_color != 'green'
                    ]

                raise UserError(_(
                    'لا يمكن إرسال المستخلص للوقف.\n\n'
                    'يوجد %d مهمة لم تُعتمد بعد من الاستشاري:\n\n'
                    '%s\n\n'
                    'يجب أن تكون جميع مهام المشروع خضراء (معتمدة) '
                    'قبل إرسال المستخلص للوقف.'
                ) % (
                    len(not_green_names),
                    '\n'.join('• ' + n for n in not_green_names),
                ))

        return super().action_submit_to_waqf()
