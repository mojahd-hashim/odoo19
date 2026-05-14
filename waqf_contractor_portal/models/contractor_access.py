from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date


class ContractorBOQAccess(models.Model):
    """
    Audited request by a contractor supervisor to access
    BOQ data for a specific mosque.
    One record per supervisor per mosque.
    """
    _name = 'contractor.boq.access'
    _description = 'Contractor BOQ Access Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'
    _rec_name = 'display_name'

    mosque_id = fields.Many2one(
        'mosque.mosque', string='Mosque',
        required=True, ondelete='cascade', index=True,
    )
    supervisor_id = fields.Many2one(
        'res.partner', string='Supervisor',
        required=True, index=True,
        domain=[('contractor_supervisor', '=', True)],
    )
    state = fields.Selection([
        ('requested',  'Requested'),
        ('granted',    'Access Granted'),
        ('revoked',    'Revoked'),
    ], string='Status', default='requested', tracking=True)

    request_date    = fields.Date(string='Request Date', default=fields.Date.today)
    grant_date      = fields.Date(string='Grant Date', readonly=True)
    granted_by      = fields.Many2one('res.users', string='Granted By', readonly=True)
    revoke_date     = fields.Date(string='Revoke Date', readonly=True)
    revoke_reason   = fields.Text(string='Revoke Reason')
    notes           = fields.Text(string='Notes')

    display_name = fields.Char(compute='_compute_display_name', store=True)

    @api.depends('mosque_id', 'supervisor_id')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = '%s — %s' % (
                rec.mosque_id.name or '', rec.supervisor_id.name or '')

    _sql_constraints = [
        ('unique_supervisor_mosque',
         'UNIQUE(mosque_id, supervisor_id)',
         'A supervisor can only have one access request per mosque.'),
    ]

    def action_grant(self):
        self.write({
            'state':      'granted',
            'grant_date': date.today(),
            'granted_by': self.env.user.id,
        })
        self.message_post(
            body=_('BOQ access granted by %s') % self.env.user.name)

    def action_revoke(self):
        self.write({
            'state':       'revoked',
            'revoke_date': date.today(),
        })

    @api.model
    def check_contractor_access(self, mosque_id, partner_id):
        return bool(self.search([
            ('mosque_id', '=', mosque_id),
            ('supervisor_id', '=', partner_id),
            ('state', '=', 'granted'),
        ], limit=1))


class ContractorWorkLog(models.Model):
    """
    Daily work entry by contractor supervisor.
    Each log = one Odoo subtask linked to a BOQ item.
    """
    _name = 'contractor.work.log'
    _description = 'Contractor Work Log'
    _inherit = ['mail.thread']
    _order = 'log_date desc, id desc'

    name = fields.Char(
        string='Work Description', required=True,
        help='Short description of work done (e.g. تغيير باب خشبي — المدخل الخلفي)',
    )
    mosque_id = fields.Many2one(
        'mosque.mosque', string='Mosque',
        required=True, index=True,
    )
    supervisor_id = fields.Many2one(
        'res.partner', string='Supervisor',
        required=True,
    )
    boq_id = fields.Many2one(
        'mosque.boq', string='BOQ Item',
        required=True,
        domain="[('mosque_id', '=', mosque_id)]",
    )
    task_id = fields.Many2one(
        'project.task', string='Main Task',
        domain="[('project_id.mosque_id', '=', mosque_id)]",
    )
    subtask_id = fields.Many2one(
        'project.task', string='Odoo Subtask',
        readonly=True, copy=False,
    )
    log_date        = fields.Date(string='Date', default=fields.Date.today, required=True)
    qty_executed    = fields.Float(string='Quantity Executed', digits=(12, 3), required=True)
    uom             = fields.Selection(related='boq_id.uom', readonly=True)
    unit_price      = fields.Float(related='boq_id.unit_price', readonly=True)
    line_value      = fields.Float(
        string='Value (SAR)',
        compute='_compute_value', store=True, digits=(16, 2),
    )
    location_detail = fields.Char(
        string='Location Detail',
        help='e.g. المدخل الخلفي، الجناح الشمالي',
    )

    state = fields.Selection([
        ('draft',     'Draft'),
        ('submitted', 'Submitted'),
        ('approved',  'Consultant Approved'),
        ('rejected',  'Rejected'),
    ], string='Status', default='draft', tracking=True)

    # Evidence photos
    photo_ids = fields.Many2many(
        'ir.attachment', string='Evidence Photos',
        domain=[('mimetype', 'like', 'image')],
    )
    photo_count  = fields.Integer(compute='_compute_photo_count')
    reject_reason = fields.Text(string='Rejection Reason')

    # Quantity validation
    qty_warning = fields.Char(compute='_compute_qty_warning')

    @api.depends('qty_executed', 'unit_price')
    def _compute_value(self):
        for rec in self:
            rec.line_value = rec.qty_executed * rec.unit_price

    @api.depends('photo_ids')
    def _compute_photo_count(self):
        for rec in self:
            rec.photo_count = len(rec.photo_ids)

    @api.depends('boq_id', 'qty_executed')
    def _compute_qty_warning(self):
        for rec in self:
            if not rec.boq_id or not rec.qty_executed:
                rec.qty_warning = False
                continue
            boq = rec.boq_id
            # Total executed including this entry
            other_logs = self.search([
                ('boq_id', '=', boq.id),
                ('state', 'in', ['submitted', 'approved']),
                ('id', '!=', rec.id or 0),
            ])
            total = sum(other_logs.mapped('qty_executed')) + rec.qty_executed
            limit = boq.contracted_qty * 1.10
            if total > limit:
                rec.qty_warning = _(
                    'إجمالي الكميات (%.1f) سيتجاوز 110%% من التعاقدية (%.1f). '
                    'يلزم أمر تغيير.') % (total, boq.contracted_qty)
            else:
                rec.qty_warning = False

    def action_submit(self):
        for rec in self:
            if not rec.photo_ids:
                raise UserError(_('يجب رفع صورة شاهد واحدة على الأقل قبل الإرسال.'))
            if rec.qty_warning:
                raise UserError(rec.qty_warning +
                                _('\nأنشئ طلب تعديل كميات أولاً.'))
            # Create subtask in Odoo Project
            subtask = rec._create_subtask()
            rec.write({'state': 'submitted', 'subtask_id': subtask.id})
            # Update BOQ executed qty
            rec.boq_id.executed_qty += rec.qty_executed

    def action_approve(self):
        self.write({'state': 'approved'})
        if self.subtask_id:
            closed_stage = self.env['project.task.type'].search(
                [('fold', '=', True)], limit=1)
            if closed_stage:
                self.subtask_id.stage_id = closed_stage

    def action_reject(self):
        self.write({'state': 'rejected'})
        # Reverse BOQ qty
        for rec in self:
            if rec.boq_id:
                rec.boq_id.executed_qty = max(
                    0, rec.boq_id.executed_qty - rec.qty_executed)

    def _create_subtask(self):
        Task = self.env['project.task']
        mosque = self.mosque_id
        project = mosque.project_id

        parent_task = self.task_id
        if not parent_task and project:
            parent_task = Task.search([
                ('project_id', '=', project.id),
                ('name', 'ilike', 'Execution'),
            ], limit=1)

        stage = self.env['project.task.type'].search(
            [('name', 'ilike', 'In Progress')], limit=1)

        subtask_vals = {
            'name':         '[%s] %s' % (self.boq_id.item_code, self.name),
            'description':  (
                'BOQ Item: %s\n'
                'Quantity: %.2f %s\n'
                'Value: SAR %.2f\n'
                'Location: %s\n'
                'Date: %s'
            ) % (
                self.boq_id.description,
                self.qty_executed,
                self.uom or '',
                self.line_value,
                self.location_detail or '—',
                str(self.log_date),
            ),
            'project_id':    project.id if project else False,
            'parent_id':     parent_task.id if parent_task else False,
            'stage_id':      stage.id if stage else False,
            'date_deadline': self.log_date,
        }
        subtask = Task.create(subtask_vals)

        # Attach photos to subtask
        for photo in self.photo_ids:
            photo.copy({'res_model': 'project.task', 'res_id': subtask.id})

        return subtask
