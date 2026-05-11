from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import timedelta


# ── Task templates per mosque ──────────────────────────────────────────────
# (name, description, days_before_end, assigned_to_field)
TASK_TEMPLATES = [
    {
        'name': 'Review & Approve Architectural Drawings',
        'description': 'Review all architectural shop drawings submitted by contractor. '
                       'Verify compliance with approved design and Saudi Building Code.',
        'tag': 'drawings_arch',
        'days_offset': -60,   # 60 days before planned_end
        'assign_to': 'resident_engineer_id',
    },
    {
        'name': 'Review & Approve MEP Drawings',
        'description': 'Review all mechanical, electrical, and plumbing shop drawings. '
                       'Verify ITP Hold Points schedule.',
        'tag': 'drawings_mep',
        'days_offset': -60,
        'assign_to': 'mep_engineer_id',
    },
    {
        'name': 'Pre-Closure Inspection — MEP',
        'description': 'Conduct mandatory pre-closure inspection before concealing MEP works. '
                       'Issue inspection certificate and sign ITP Hold Point.',
        'tag': 'pre_closure',
        'days_offset': -30,
        'assign_to': 'mep_engineer_id',
    },
    {
        'name': 'QCP & ITP Submission Review',
        'description': 'Review contractor Quality Control Plan and Inspection & Test Plan. '
                       'Approve within 15 working days of mobilization.',
        'tag': 'qcp_itp',
        'days_offset': -70,
        'assign_to': 'resident_engineer_id',
    },
    {
        'name': 'Baseline Schedule Review',
        'description': 'Review and approve contractor baseline schedule within 10 working days '
                       'of site handover. Flag any conflicts with contract milestones.',
        'tag': 'baseline_sched',
        'days_offset': -75,
        'assign_to': 'resident_engineer_id',
    },
    {
        'name': 'Punch List — Pre Initial Handover',
        'description': 'Prepare and issue punch list before initial handover. '
                       'All items must be closed before final handover.',
        'tag': 'punch_list',
        'days_offset': -14,
        'assign_to': 'resident_engineer_id',
    },
    {
        'name': 'As-Built Drawings Review',
        'description': 'Review and approve as-built drawings submitted by contractor. '
                       'Required before final handover recommendation.',
        'tag': 'as_built',
        'days_offset': -7,
        'assign_to': 'resident_engineer_id',
    },
]

# ── Milestone definitions ──────────────────────────────────────────────────
# (name, state_trigger, days_offset_from_planned_end, sequence)
MILESTONE_DEFS = [
    ('Renovation Permit Received',   'mobilizing',  None,  1),
    ('Contractor Site Mobilization', 'mobilizing',  -75,   2),
    ('Execution Started',            'active',      -74,   3),
    ('Architectural Works Complete', 'active',      -20,   4),
    ('MEP Works Complete',           'active',      -15,   5),
    ('Punch List Closed',            'active',      -7,    6),
    ('Initial Handover',             'initial_hov', 0,     7),
    ('Final Handover & Close',       'final_hov',   14,    8),
]


class MosqueMosqueProject(models.Model):
    """
    Extends mosque.mosque to add Odoo Project integration.
    Inherits from the base mosque model — does NOT duplicate fields.
    """
    _inherit = 'mosque.mosque'

    # ── Project link ──────────────────────────────────────────────
    project_id = fields.Many2one(
        'project.project',
        string='Odoo Project',
        readonly=True,
        copy=False,
        ondelete='set null',
        help='Auto-created Odoo Project linked to this mosque rehabilitation project.',
    )
    task_count = fields.Integer(
        string='Tasks',
        compute='_compute_task_count',
    )
    milestone_count = fields.Integer(
        string='Milestones',
        compute='_compute_task_count',
    )
    project_progress = fields.Float(
        string='Project Task Progress (%)',
        compute='_compute_task_count',
        help='Percentage of tasks marked as done in the linked Odoo Project.',
    )

    # ── Compute task/milestone counts ──────────────────────────────
    @api.depends('project_id', 'project_id.task_ids',
                 'project_id.milestone_ids')
    def _compute_task_count(self):
        for rec in self:
            if rec.project_id:
                tasks = rec.project_id.task_ids.filtered(
                    lambda t: not t.milestone_id)
                done  = tasks.filtered(
                    lambda t: t.stage_id.is_closed)
                rec.task_count      = len(tasks)
                rec.milestone_count = len(rec.project_id.milestone_ids)
                rec.project_progress = (
                    len(done) / len(tasks) * 100) if tasks else 0.0
            else:
                rec.task_count      = 0
                rec.milestone_count = 0
                rec.project_progress = 0.0

    # ══════════════════════════════════════════════════════════════
    # OVERRIDE: action_mobilize — creates the Odoo Project
    # ══════════════════════════════════════════════════════════════
    def action_mobilize(self):
        for mosque in self:
            if mosque.project_id:
                raise UserError(
                    _('Mosque "%s" already has a linked project: %s')
                    % (mosque.name, mosque.project_id.name))

            project = self._create_mosque_project(mosque)
            mosque.project_id = project

        # Call super AFTER creating project so state changes to 'mobilizing'
        return super().action_mobilize()

    # ══════════════════════════════════════════════════════════════
    # OVERRIDE: state transitions — sync milestone completion
    # ══════════════════════════════════════════════════════════════
    def action_start(self):
        result = super().action_start()
        self._sync_milestone('active')
        return result

    def action_initial_handover(self):
        result = super().action_initial_handover()
        self._sync_milestone('initial_hov')
        return result

    def action_final_handover(self):
        result = super().action_final_handover()
        self._sync_milestone('final_hov')
        self._close_project()
        return result

    # ══════════════════════════════════════════════════════════════
    # PROJECT CREATION LOGIC
    # ══════════════════════════════════════════════════════════════
    def _create_mosque_project(self, mosque):
        Project = self.env['project.project']

        # Resolve user from resident engineer
        manager_user = (mosque.resident_engineer_id.user_id
                        or self.env.user)

        # Get or create project tags
        tag_waqf = self._get_or_create_tag('Waqf Mosque Rehab')
        tag_city  = self._get_or_create_tag(
            dict(mosque._fields['city'].selection).get(mosque.city, mosque.city))

        project = Project.create({
            'name':        '[%s] %s' % (mosque.code, mosque.name),
            'user_id':     manager_user.id,
            'date_start':  mosque.planned_start,
            'date':        mosque.planned_end,
            'description': self._build_project_description(mosque),
            'tag_ids':     [(6, 0, [tag_waqf.id, tag_city.id])],
            'privacy_visibility': 'employees',
        })

        # Create milestones
        self._create_milestones(project, mosque)

        # Create standard tasks
        self._create_standard_tasks(project, mosque)

        # Create recurring task stubs (weekly report, monthly cert)
        self._create_recurring_stubs(project, mosque)

        return project

    def _get_or_create_tag(self, name):
        Tag = self.env['project.tags']
        tag = Tag.search([('name', '=', name)], limit=1)
        if not tag:
            tag = Tag.create({'name': name})
        return tag

    def _build_project_description(self, mosque):
        return (
            '<p><strong>Mosque Rehabilitation Project</strong></p>'
            '<ul>'
            '<li>Code: %s</li>'
            '<li>City: %s</li>'
            '<li>Package: %s</li>'
            '<li>Contract Value: SAR %s</li>'
            '<li>Contractor: %s</li>'
            '<li>Resident Engineer: %s</li>'
            '</ul>'
        ) % (
            mosque.code,
            dict(mosque._fields['city'].selection).get(mosque.city, ''),
            mosque.package_id.name or '—',
            '{:,.0f}'.format(mosque.contract_value),
            mosque.contractor or '—',
            mosque.resident_engineer_id.name or '—',
        )

    # ── Milestones ────────────────────────────────────────────────
    def _create_milestones(self, project, mosque):
        Milestone = self.env['project.milestone']
        planned_end   = mosque.planned_end
        planned_start = mosque.planned_start

        for name, state_trigger, days_offset, seq in MILESTONE_DEFS:
            if days_offset is None:
                # Special case: permit date
                deadline = mosque.permit_date or planned_start
            elif days_offset <= 0:
                deadline = (planned_end + timedelta(days=days_offset)
                            if planned_end else None)
            else:
                deadline = (planned_end + timedelta(days=days_offset)
                            if planned_end else None)

            Milestone.create({
                'name':           name,
                'project_id':     project.id,
                'deadline':       deadline,
                'is_reached':     False,
            })

    # ── Standard Tasks ────────────────────────────────────────────
    def _create_standard_tasks(self, project, mosque):
        Task  = self.env['project.task']
        Stage = self._get_default_stage(project)

        planned_end = mosque.planned_end

        for tmpl in TASK_TEMPLATES:
            # Resolve assignee
            engineer = getattr(mosque, tmpl['assign_to'], False)
            user_ids  = [(4, engineer.user_id.id)] if engineer and engineer.user_id else []

            deadline = (planned_end + timedelta(days=tmpl['days_offset'])
                        if planned_end else None)

            Task.create({
                'name':         tmpl['name'],
                'description':  tmpl['description'],
                'project_id':   project.id,
                'stage_id':     Stage.id if Stage else False,
                'user_ids':     user_ids,
                'date_deadline': deadline,
                'tag_ids':      [(6, 0, [self._get_or_create_task_tag(tmpl['tag']).id])],
            })

    def _create_recurring_stubs(self, project, mosque):
        """
        Create placeholder tasks for recurring duties.
        Actual recurrence is set manually by the project manager.
        """
        Task  = self.env['project.task']
        Stage = self._get_default_stage(project)
        engineer = mosque.resident_engineer_id
        user_ids = [(4, engineer.user_id.id)] if engineer and engineer.user_id else []

        stubs = [
            {
                'name': '📋 Weekly Quality & Safety Report (Template)',
                'description': (
                    'Submit weekly quality report covering:\n'
                    '- Tests conducted and results\n'
                    '- NCR count and status\n'
                    '- Safety incidents and corrective actions\n'
                    '- ITP Hold Points closed\n\n'
                    'Duplicate this task each week.'
                ),
            },
            {
                'name': '💰 Monthly Payment Certificate (Template)',
                'description': (
                    'Prepare and submit monthly payment certificate:\n'
                    '1. Update executed quantities in BOQ\n'
                    '2. Create certificate in Financial → Payment Certificates\n'
                    '3. Attach supporting evidence photos\n'
                    '4. Submit to consultant for review\n\n'
                    'Duplicate this task each month.'
                ),
            },
            {
                'name': '📷 Site Visit Log — Weekly (Template)',
                'description': (
                    'Log this week\'s field visits:\n'
                    '- Minimum 2 validated visits per mosque per week\n'
                    '- Each visit must be GPS + QR validated\n'
                    '- Upload site photos\n\n'
                    'Duplicate this task each week.'
                ),
            },
        ]

        for stub in stubs:
            Task.create({
                'name':        stub['name'],
                'description': stub['description'],
                'project_id':  project.id,
                'stage_id':    Stage.id if Stage else False,
                'user_ids':    user_ids,
            })

    def _get_default_stage(self, project):
        Stage = self.env['project.task.type']
        stage = Stage.search(
            [('project_ids', 'in', project.id)], limit=1, order='sequence asc')
        if not stage:
            # Fallback: get any global stage
            stage = Stage.search([], limit=1, order='sequence asc')
        return stage

    def _get_or_create_task_tag(self, name):
        Tag = self.env['project.tags']
        tag = Tag.search([('name', '=', name)], limit=1)
        if not tag:
            tag = Tag.create({'name': name})
        return tag

    # ── Milestone sync on state change ────────────────────────────
    def _sync_milestone(self, state_trigger):
        for mosque in self:
            if not mosque.project_id:
                continue
            milestones = mosque.project_id.milestone_ids
            state_map = {
                'active':      ['Execution Started'],
                'initial_hov': ['Initial Handover', 'Punch List Closed'],
                'final_hov':   ['Final Handover & Close', 'As-Built Drawings Review'],
            }
            names_to_reach = state_map.get(state_trigger, [])
            for ms in milestones:
                if any(n in ms.name for n in names_to_reach):
                    ms.is_reached = True

    def _close_project(self):
        for mosque in self:
            if mosque.project_id:
                mosque.project_id.last_update_status = 'done'

    # ── Smart button action ───────────────────────────────────────
    def action_view_project(self):
        self.ensure_one()
        if not self.project_id:
            raise UserError(_('No project linked yet. Click "Mobilize" to create one.'))
        return {
            'type': 'ir.actions.act_window',
            'name': self.project_id.name,
            'res_model': 'project.project',
            'res_id': self.project_id.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_view_tasks(self):
        self.ensure_one()
        if not self.project_id:
            raise UserError(_('No project linked yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Tasks — %s') % self.name,
            'res_model': 'project.task',
            'view_mode': 'list,form,kanban,gantt',
            'domain': [('project_id', '=', self.project_id.id)],
            'context': {'default_project_id': self.project_id.id},
        }

    def action_view_milestones(self):
        self.ensure_one()
        if not self.project_id:
            raise UserError(_('No project linked yet.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Milestones — %s') % self.name,
            'res_model': 'project.milestone',
            'view_mode': 'list,form',
            'domain': [('project_id', '=', self.project_id.id)],
            'context': {'default_project_id': self.project_id.id},
        }

    # ── Unlink: archive project too ───────────────────────────────
    def unlink(self):
        projects = self.mapped('project_id')
        result = super().unlink()
        if projects:
            projects.write({'active': False})
        return result


# ══════════════════════════════════════════════════════════════════════
# Extend project.project to show linked mosque
# ══════════════════════════════════════════════════════════════════════
class ProjectProjectMosque(models.Model):
    _inherit = 'project.project'

    mosque_id = fields.Many2one(
        'mosque.mosque',
        string='Linked Mosque',
        compute='_compute_mosque_id',
        store=True,
    )
    mosque_kpi = fields.Float(
        string='Mosque KPI (%)',
        related='mosque_id.overall_kpi',
        store=True,
    )
    mosque_state = fields.Selection(
        related='mosque_id.state',
        string='Mosque Status',
        store=True,
    )
    mosque_financial_pct = fields.Float(
        related='mosque_id.financial_progress',
        string='Financial Progress (%)',
        store=True,
    )
    mosque_days_delay = fields.Integer(
        related='mosque_id.days_delay',
        string='Days Delay',
        store=True,
    )

    @api.depends('name')
    def _compute_mosque_id(self):
        Mosque = self.env['mosque.mosque']
        for proj in self:
            mosque = Mosque.search(
                [('project_id', '=', proj.id)], limit=1)
            proj.mosque_id = mosque


# ══════════════════════════════════════════════════════════════════════
# Extend project.task — link back to mosque
# ══════════════════════════════════════════════════════════════════════
class ProjectTaskMosque(models.Model):
    _inherit = 'project.task'

    mosque_id = fields.Many2one(
        'mosque.mosque',
        string='Mosque',
        related='project_id.mosque_id',
        store=True,
        readonly=True,
    )
    mosque_code = fields.Char(
        related='mosque_id.code',
        string='Mosque Code',
        store=True,
        readonly=True,
    )
