from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import date


class ProjectTaskType(models.Model):
    """
    Extend task stages to add Waqf-specific metadata:
    - is_consultant_review : tasks here need consultant approval
    - is_waqf_approval     : tasks here need Waqf final approval
    - require_green        : cannot enter this stage unless task is green
    """
    _inherit = 'project.task.type'

    waqf_stage = fields.Selection([
        ('todo',              'To Do'),
        ('in_progress',       'In Progress'),
        ('consultant_review', 'Consultant Review'),
        ('waqf_approval',     'Waqf Approval'),
        ('done',              'Done'),
    ], string='Waqf Stage', default=False,
       help='Maps this stage to the Waqf workflow.')

    require_green = fields.Boolean(
        string='Require Green Before Entry',
        default=False,
        help='If checked, a task cannot move into this stage '
             'unless its kanban_color is green (approved).',
    )
    is_closing_stage = fields.Boolean(
        string='Closing Stage',
        default=False,
        help='Tasks in this stage are considered complete.',
    )


class ProjectTask(models.Model):
    """
    Extend project.task with:
    - kanban_color   : computed color state (grey/green/red/yellow/orange)
    - review fields  : consultant approval, rejection reason
    - CO blocking    : linked change order prevents stage transition
    - stage guard    : blocks move to require_green stage if not approved
    """
    _inherit = 'project.task'

    # ── Review state ──────────────────────────────────────────────
    review_state = fields.Selection([
        ('pending',   'No Update Yet'),
        ('submitted', 'Update Submitted'),
        ('approved',  'Consultant Approved'),
        ('rejected',  'Rejected'),
        ('blocked',   'Blocked — CO Pending'),
    ], string='Review State',
       default='pending',
       tracking=True,
       help='Drives the kanban color of this task.',
    )

    rejection_note = fields.Text(
        string='Rejection Reason',
        help='Filled by consultant when rejecting a task update.',
    )
    approved_by = fields.Many2one(
        'res.users', string='Approved By', readonly=True,
    )
    approved_date = fields.Date(string='Approved Date', readonly=True)

    # ── CO blocking ───────────────────────────────────────────────
    blocking_co_id = fields.Many2one(
        'mosque.change.order',
        string='Blocking Change Order',
        help='When set, this task is frozen until the CO is approved.',
    )
    is_blocked_by_co = fields.Boolean(
        string='Blocked by CO',
        compute='_compute_blocked_by_co',
        store=True,
    )

    # ── Kanban color ──────────────────────────────────────────────
    kanban_color = fields.Selection([
        ('grey',   'Grey — No Update'),
        ('green',  'Green — Approved'),
        ('red',    'Red — Rejected'),
        ('yellow', 'Yellow — CO Pending'),
        ('orange', 'Orange — Overdue'),
    ], string='Kanban Color',
       compute='_compute_kanban_color',
       store=True,
    )

    # Subtask counts for quick view
    pending_subtask_count = fields.Integer(
        compute='_compute_subtask_counts', string='Pending Subtasks',
    )
    approved_subtask_count = fields.Integer(
        compute='_compute_subtask_counts', string='Approved Subtasks',
    )
    rejected_subtask_count = fields.Integer(
        compute='_compute_subtask_counts', string='Rejected Subtasks',
    )
    subtasks_all_green = fields.Boolean(
        compute='_compute_subtask_counts',
        string='All Subtasks Approved',
        store=True,
        help='True when all subtasks are approved — unlocks Waqf Approval stage.',
    )
    subtasks_blocking_html = fields.Html(
        compute='_compute_subtask_counts',
        string='Blocking Subtasks',
    )

    # ── Compute: CO blocking ──────────────────────────────────────
    @api.depends('blocking_co_id', 'blocking_co_id.state')
    def _compute_blocked_by_co(self):
        for task in self:
            task.is_blocked_by_co = bool(
                task.blocking_co_id and
                task.blocking_co_id.state not in ('approved', 'rejected')
            )

    # ── Compute: kanban color ─────────────────────────────────────
    @api.depends(
        'review_state', 'is_blocked_by_co',
        'date_deadline', 'stage_id.is_closed',
        'child_ids', 'child_ids.review_state',
        'child_ids.is_blocked_by_co',
        'parent_id',
    )
    def _compute_kanban_color(self):
        today = fields.Date.today()
        for task in self:

            # ── SUBTASK: color from own review_state ──────────────
            if task.parent_id:
                if task.is_blocked_by_co:
                    task.kanban_color = 'yellow'
                elif task.review_state == 'approved':
                    task.kanban_color = 'green'
                elif task.review_state == 'rejected':
                    task.kanban_color = 'red'
                elif (task.date_deadline and
                      task.date_deadline < today and
                      not task.stage_id.is_closed):
                    task.kanban_color = 'orange'
                else:
                    task.kanban_color = 'grey'
                continue

            # ── MAIN TASK: color derived from subtasks ────────────
            subtasks = task.child_ids
            if not subtasks:
                # No subtasks yet — check own state
                if task.is_blocked_by_co:
                    task.kanban_color = 'yellow'
                elif task.review_state == 'approved':
                    task.kanban_color = 'green'
                elif task.review_state == 'rejected':
                    task.kanban_color = 'red'
                elif (task.date_deadline and
                      task.date_deadline.date() < today and
                      not task.stage_id.is_closed):
                    task.kanban_color = 'orange'
                else:
                    task.kanban_color = 'grey'
                continue

            # Derive color from subtask states — priority order:
            # yellow (blocked) > red (rejected) > grey (pending) > green (all ok)
            has_blocked  = any(s.is_blocked_by_co for s in subtasks)
            has_rejected = any(s.review_state == 'rejected' for s in subtasks)
            has_pending  = any(
                s.review_state in ('pending', 'submitted')
                for s in subtasks
            )
            all_approved = all(s.review_state == 'approved' for s in subtasks)

            if has_blocked:
                task.kanban_color = 'yellow'
            elif has_rejected:
                task.kanban_color = 'red'
            elif all_approved:
                task.kanban_color = 'green'
            elif (task.date_deadline and
                  task.date_deadline < today and
                  not task.stage_id.is_closed):
                task.kanban_color = 'orange'
            else:
                task.kanban_color = 'grey'

    # ── Compute: subtask counts ───────────────────────────────────
    @api.depends('child_ids', 'child_ids.review_state', 'child_ids.kanban_color')
    def _compute_subtask_counts(self):
        color_labels = {
            'grey':   ('⚪', 'لم تُعتمد بعد'),
            'red':    ('🔴', 'مرفوضة'),
            'yellow': ('🟡', 'مجمّدة — CO معلق'),
            'orange': ('🟠', 'متأخرة'),
        }
        for task in self:
            subtasks = task.child_ids
            if not subtasks:
                task.pending_subtask_count  = 0
                task.approved_subtask_count = 0
                task.rejected_subtask_count = 0
                task.subtasks_all_green     = False
                task.subtasks_blocking_html = ''
                continue

            pending  = subtasks.filtered(
                lambda s: s.review_state in ('pending', 'submitted'))
            approved = subtasks.filtered(
                lambda s: s.review_state == 'approved')
            rejected = subtasks.filtered(
                lambda s: s.review_state == 'rejected')
            not_green = subtasks.filtered(
                lambda s: s.review_state != 'approved')

            task.pending_subtask_count  = len(pending)
            task.approved_subtask_count = len(approved)
            task.rejected_subtask_count = len(rejected)
            task.subtasks_all_green     = len(not_green) == 0

            # Build blocking HTML
            if not_green:
                lines = []
                for s in not_green:
                    icon, label = color_labels.get(
                        s.kanban_color, ('⚪', 'غير معتمدة'))
                    lines.append(
                        '<li>%s <b>%s</b> — %s</li>' % (icon, s.name, label))
                task.subtasks_blocking_html = (
                    '<ul style="margin:4px 0;padding-right:16px">%s</ul>'
                    % ''.join(lines))
            else:
                task.subtasks_blocking_html = ''

    # ══════════════════════════════════════════════════════════════
    # STAGE TRANSITION GUARD
    # ══════════════════════════════════════════════════════════════
    def write(self, vals):
        if 'stage_id' in vals and not self.env.context.get('bypass_stage_guard'):
            new_stage = self.env['project.task.type'].browse(vals['stage_id'])

            for task in self:
                # Only apply guard to MAIN tasks (not subtasks)
                if task.parent_id:
                    continue

                # Block entry to stages that require green
                if new_stage.require_green and task.kanban_color != 'green':

                    # Build list of non-green subtasks for clear message
                    subtasks = task.child_ids
                    if subtasks:
                        not_green = subtasks.filtered(
                            lambda s: s.review_state != 'approved')
                        color_map = {
                            'grey':   'لم تُعتمد بعد',
                            'red':    'مرفوضة',
                            'yellow': 'مجمّدة — CO معلق',
                            'orange': 'متأخرة',
                        }
                        detail = '\n'.join(
                            '• %s — %s' % (
                                s.name,
                                color_map.get(s.kanban_color, s.kanban_color)
                            )
                            for s in not_green
                        )
                        raise UserError(_(
                            'لا يمكن نقل المهمة "%s" إلى مرحلة "%s".\n\n'
                            'المهام الفرعية التالية لم تُعتمد بعد:\n\n%s\n\n'
                            'يجب اعتماد جميع المهام الفرعية من الاستشاري أولاً.'
                        ) % (task.name, new_stage.name, detail))
                    else:
                        raise UserError(_(
                            'لا يمكن نقل المهمة "%s" إلى مرحلة "%s".\n\n'
                            'المهمة ليست خضراء بعد — يجب اعتمادها من الاستشاري أولاً.'
                        ) % (task.name, new_stage.name))

                # Block any movement if CO is pending
                if (task.is_blocked_by_co and
                        vals.get('stage_id') != task.stage_id.id):
                    raise UserError(_(
                        'المهمة "%s" مجمّدة بسبب أمر التغيير: %s\n'
                        'يجب اعتماد أمر التغيير أولاً.'
                    ) % (task.name, task.blocking_co_id.name))

        return super().write(vals)

    # ══════════════════════════════════════════════════════════════
    # CONSULTANT ACTIONS
    # ══════════════════════════════════════════════════════════════
    def action_consultant_approve(self):
        """
        Consultant approves a subtask → updates its color.
        If ALL subtasks of parent are now green → parent turns green
        and moves to Waqf Approval automatically.
        """
        self.ensure_one()

        if self.is_blocked_by_co:
            raise UserError(_(
                'لا يمكن الاعتماد — المهمة مجمّدة بسبب أمر التغيير: %s'
            ) % self.blocking_co_id.name)

        # Approve this task / subtask
        self.write({
            'review_state':   'approved',
            'approved_by':    self.env.user.id,
            'approved_date':  date.today(),
            'rejection_note': False,
        })

        self.message_post(
            body=_('✅ اعتمد الاستشاري <b>%s</b> هذه المهمة.')
                 % self.env.user.name,
        )

        # Notify supervisor
        self._notify_supervisor_approved()

        # ── If this is a SUBTASK → check if parent is now all-green ──
        if self.parent_id:
            self._check_and_promote_parent()

        # ── If this is a MAIN TASK with no subtasks → move to Waqf ──
        elif not self.child_ids:
            self._move_to_waqf_approval()

        return True

    def _check_and_promote_parent(self):
        """
        After approving a subtask, check if all siblings are green.
        If yes, promote the parent main task to Waqf Approval.
        """
        parent = self.parent_id
        if not parent:
            return

        siblings = parent.child_ids
        all_green = all(s.review_state == 'approved' for s in siblings)

        if all_green:
            parent.message_post(
                body=_('✅ جميع المهام الفرعية (%d) معتمدة — '
                        'المهمة الرئيسية جاهزة للوقف.') % len(siblings),
            )
            parent._move_to_waqf_approval()

    def _move_to_waqf_approval(self):
        """Move main task to Waqf Approval stage."""
        waqf_stage = self.env['project.task.type'].search([
            ('waqf_stage', '=', 'waqf_approval'),
            '|',
            ('project_ids', 'in', self.project_id.id),
            ('project_ids', '=', False),
        ], limit=1, order='sequence asc')

        if waqf_stage:
            # Temporarily bypass guard — we already verified green
            super(ProjectTask, self).write({'stage_id': waqf_stage.id})
            self.message_post(
                body=_('🔄 تم نقل المهمة تلقائياً إلى مرحلة '
                        '"Waqf Approval" — بانتظار الاعتماد النهائي.'),
            )

    def action_consultant_reject(self):
        """Open rejection wizard to enter reason."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('رفض المهمة — أدخل السبب'),
            'res_model': 'waqf.task.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_id': self.id,
                'default_reject_type': 'consultant',
            },
        }

    # ══════════════════════════════════════════════════════════════
    # WAQF ACTIONS
    # ══════════════════════════════════════════════════════════════
    def action_waqf_approve(self):
        """Waqf final approval — task moves to Done."""
        self.ensure_one()

        if self.kanban_color != 'green':
            raise UserError(_(
                'لا يمكن اعتماد المهمة من الوقف — '
                'يجب أن تكون معتمدة من الاستشاري أولاً (خضراء).'
            ))

        done_stage = self.env['project.task.type'].search([
            ('waqf_stage', '=', 'done'),
            ('project_ids', 'in', self.project_id.id),
        ], limit=1)

        if not done_stage:
            done_stage = self.env['project.task.type'].search([
                ('waqf_stage', '=', 'done'),
            ], limit=1)

        vals = {'review_state': 'approved'}
        if done_stage:
            vals['stage_id'] = done_stage.id

        self.write(vals)
        self.message_post(
            body=_('✅ اعتمد الوقف هذه المهمة نهائياً. '
                   'تم نقلها لمرحلة Done.'),
        )

    def action_waqf_reject(self):
        """Waqf rejects — task goes back to Consultant Review."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('رفض الوقف — أدخل السبب'),
            'res_model': 'waqf.task.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_task_id': self.id,
                'default_reject_type': 'waqf',
            },
        }

    # ══════════════════════════════════════════════════════════════
    # CO BLOCKING
    # ══════════════════════════════════════════════════════════════
    def action_block_with_co(self, co_id):
        """Block task with a change order."""
        self.write({
            'review_state':   'blocked',
            'blocking_co_id': co_id,
        })
        co = self.env['mosque.change.order'].browse(co_id)
        self.message_post(
            body=_('🔒 المهمة مجمّدة — بانتظار اعتماد أمر التغيير: <b>%s</b>') % co.name,
        )

    def action_unblock_co(self):
        """Called automatically when linked CO is approved."""
        for task in self:
            if task.blocking_co_id and task.blocking_co_id.state == 'approved':
                task.write({
                    'review_state':   'pending',
                    'blocking_co_id': False,
                })
                task.message_post(
                    body=_('🔓 تم رفع التجميد — أمر التغيير المرتبط تم اعتماده. '
                           'يمكن استئناف العمل.'),
                )

    # ══════════════════════════════════════════════════════════════
    # NOTIFICATIONS
    # ══════════════════════════════════════════════════════════════
    def _notify_supervisor_approved(self):
        """Post approval notification on linked work logs."""
        WorkLog = self.env['contractor.work.log'].sudo()
        logs = WorkLog.search([('subtask_id', '=', self.id)])
        for log in logs:
            log.message_post(
                body=_('✅ اعتمد الاستشاري العمل: <b>%s</b>') % log.name,
                subtype_xmlid='mail.mt_comment',
            )

    def _notify_supervisor_rejected(self, reason, reject_type='consultant'):
        """Post rejection notification on linked work logs."""
        WorkLog = self.env['contractor.work.log'].sudo()
        logs = WorkLog.search([('subtask_id', '=', self.id)])
        who = _('الاستشاري') if reject_type == 'consultant' else _('الوقف')
        for log in logs:
            log.write({'reject_reason': reason, 'state': 'rejected'})
            log.message_post(
                body=_('❌ رفض %s العمل: <b>%s</b><br/>'
                       '<b>السبب:</b> %s') % (who, log.name, reason),
                subtype_xmlid='mail.mt_comment',
            )


# ══════════════════════════════════════════════════════════════════
# CHANGE ORDER — auto-unblock tasks on approval
# ══════════════════════════════════════════════════════════════════
class MosqueChangeOrderReview(models.Model):
    _inherit = 'mosque.change.order'

    def action_approve(self):
        result = super().action_approve()
        # Unblock all tasks linked to this CO
        tasks = self.env['project.task'].search([
            ('blocking_co_id', '=', self.id)
        ])
        tasks.action_unblock_co()
        return result


# ══════════════════════════════════════════════════════════════════
# REJECTION WIZARD
# ══════════════════════════════════════════════════════════════════
class WaqfTaskRejectWizard(models.TransientModel):
    _name = 'waqf.task.reject.wizard'
    _description = 'Task Rejection Wizard'

    task_id     = fields.Many2one('project.task', required=True)
    reject_type = fields.Selection([
        ('consultant', 'Consultant'),
        ('waqf',       'Waqf'),
    ], required=True, default='consultant')
    reason = fields.Text(
        string='سبب الرفض',
        required=True,
        help='سيُرسَل هذا السبب للمشرف الميداني تلقائياً.',
    )

    def action_confirm_reject(self):
        task = self.task_id

        # Find target stage based on reject type
        if self.reject_type == 'consultant':
            target_waqf_stage = 'in_progress'
        else:
            target_waqf_stage = 'consultant_review'

        target_stage = self.env['project.task.type'].search([
            ('waqf_stage', '=', target_waqf_stage),
            ('project_ids', 'in', task.project_id.id),
        ], limit=1)

        if not target_stage:
            target_stage = self.env['project.task.type'].search([
                ('waqf_stage', '=', target_waqf_stage),
            ], limit=1)

        vals = {
            'review_state':   'rejected',
            'rejection_note': self.reason,
        }
        if target_stage:
            # Temporarily bypass the guard for rejection (going backwards)
            task.with_context(bypass_stage_guard=True).write(
                {'stage_id': target_stage.id})

        task.write(vals)

        who = _('الاستشاري') if self.reject_type == 'consultant' else _('الوقف')
        task.message_post(
            body=_('❌ رفض %s هذه المهمة.<br/>'
                   '<b>السبب:</b> %s') % (who, self.reason),
        )

        # Notify supervisor via work log
        task._notify_supervisor_rejected(self.reason, self.reject_type)

        return {'type': 'ir.actions.act_window_close'}
