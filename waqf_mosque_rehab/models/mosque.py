from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date
import math


class MosquePackage(models.Model):
    _name = 'mosque.package'
    _description = 'Geographic Package'
    _order = 'sequence'

    name = fields.Char(string='Package Name', required=True, translate=True)
    code = fields.Char(string='Package Code', required=True)
    sequence = fields.Integer(default=10)
    phase = fields.Selection([
        ('1', 'Phase 1 — North Riyadh'),
        ('2', 'Phase 2 — South & Central Riyadh'),
        ('3', 'Phase 3 — East Riyadh'),
        ('4', 'Phase 4 — West Riyadh & Provinces'),
    ], string='Phase', required=True)
    planned_start = fields.Date(string='Planned Start')
    planned_end = fields.Date(string='Planned End')
    mosque_ids = fields.One2many('mosque.mosque', 'package_id', string='Mosques')
    mosque_count = fields.Integer(compute='_compute_mosque_count', string='Mosques #')
    color = fields.Integer(string='Color')

    @api.depends('mosque_ids')
    def _compute_mosque_count(self):
        for rec in self:
            rec.mosque_count = len(rec.mosque_ids)


class MosqueMosque(models.Model):
    _name = 'mosque.mosque'
    _description = 'Mosque'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'code'

    # ── Identification ────────────────────────────────────────────
    name = fields.Char(string='Mosque Name', required=True, tracking=True,translate=True)
    code = fields.Char(string='Code', required=True, copy=False,
                       default=lambda self: 'New')
    package_id = fields.Many2one('mosque.package', string='Package',
                                 required=True, tracking=True)
    phase = fields.Selection(related='package_id.phase', store=True,
                             string='Phase')

    # ── Location ──────────────────────────────────────────────────
    city = fields.Selection([
        ('riyadh',   'Riyadh'),
        ('jeddah',   'Jeddah'),
        ('taif',     'Taif'),
        ('jazan',    'Jazan'),
        ('yara',     'Yara — Khamis Mushait'),
        ('aflaj',    'Al-Aflaj'),
        ('rafha',    'Rafha'),
    ], string='City', required=True, tracking=True)
    district = fields.Char(string='District / Neighborhood')
    latitude  = fields.Float(string='Latitude',  digits=(10, 7))
    longitude = fields.Float(string='Longitude', digits=(10, 7))
    geofence_radius = fields.Integer(string='Geofence Radius (m)', default=100)
    qr_code = fields.Char(string='QR Code Token', copy=False,
                          default=lambda self: self.env['ir.sequence'].next_by_code('mosque.qr'))

    # ── Contract ──────────────────────────────────────────────────
    contract_value = fields.Monetary(string='Contract Value (SAR)',
                                     currency_field='currency_id', tracking=True)
    currency_id = fields.Many2one('res.currency', default=lambda s: s.env.ref('base.SAR'))
    planned_start  = fields.Date(string='Planned Start', tracking=True)
    planned_end    = fields.Date(string='Planned End',   tracking=True)
    actual_start   = fields.Date(string='Actual Start')
    actual_end     = fields.Date(string='Actual End')

    # ── Team ──────────────────────────────────────────────────────
    resident_engineer_id = fields.Many2one('hr.employee',
                                           string='Resident Engineer',
                                           domain=[('job_id.name', 'ilike', 'engineer')])
    mep_engineer_id = fields.Many2one('hr.employee', string='MEP Engineer')
    contractor = fields.Char(string='Contractor Name')

    # ── Status ────────────────────────────────────────────────────
    state = fields.Selection([
        ('draft',       'Draft'),
        ('mobilizing',  'Mobilization'),
        ('active',      'Under Execution'),
        ('initial_hov', 'Initial Handover'),
        ('final_hov',   'Final Handover'),
        ('warranty',    'Warranty Period'),
        ('closed',      'Closed'),
    ], string='Status', default='draft', tracking=True, required=True)

    # ── Progress (computed) ────────────────────────────────────────
    boq_ids             = fields.One2many('mosque.boq', 'mosque_id', string='BOQ Lines')
    supervision_ids     = fields.One2many('mosque.supervision', 'mosque_id', string='Supervision Reports')
    certificate_ids     = fields.One2many('mosque.certificate', 'mosque_id', string='Certificates')
    change_order_ids    = fields.One2many('mosque.change.order', 'mosque_id', string='Change Orders')
    attendance_ids      = fields.One2many('mosque.attendance', 'mosque_id', string='Attendance Logs')

    financial_progress  = fields.Float(string='Financial Progress (%)',
                                       compute='_compute_progress', store=True)
    time_progress       = fields.Float(string='Time Progress (%)',
                                       compute='_compute_progress', store=True)
    visit_compliance    = fields.Float(string='Visit Compliance (%)',
                                       compute='_compute_progress', store=True)
    overall_kpi         = fields.Float(string='Overall KPI (%)',
                                       compute='_compute_progress', store=True)
    kpi_color           = fields.Char(compute='_compute_kpi_color')

    boq_count           = fields.Integer(compute='_compute_counts')
    certificate_count   = fields.Integer(compute='_compute_counts')
    supervision_count   = fields.Integer(compute='_compute_counts')
    change_order_count  = fields.Integer(compute='_compute_counts')

    certified_amount    = fields.Monetary(compute='_compute_progress', store=True,
                                          currency_field='currency_id',
                                          string='Certified Amount')
    total_boq_value     = fields.Monetary(compute='_compute_progress', store=True,
                                          currency_field='currency_id',
                                          string='Total BOQ Value')
    change_order_value  = fields.Monetary(compute='_compute_progress', store=True,
                                          currency_field='currency_id',
                                          string='Change Orders Value')
    days_delay          = fields.Integer(compute='_compute_progress', store=True,
                                         string='Days Delay')

    permit_date         = fields.Date(string='Renovation Permit Date')
    permit_number       = fields.Char(string='Permit Number')
    notes               = fields.Text(string='Notes')
    active              = fields.Boolean(default=True)

    # ── Sequence ──────────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code', 'New') == 'New':
                vals['code'] = self.env['ir.sequence'].next_by_code('mosque.mosque') or 'New'
        return super().create(vals_list)

    # ── Progress computation ───────────────────────────────────────
    @api.depends(
        'boq_ids.executed_qty', 'boq_ids.contracted_qty', 'boq_ids.unit_price',
        'certificate_ids.state', 'certificate_ids.certified_amount',
        'attendance_ids', 'planned_start', 'planned_end',
        'change_order_ids.amount', 'change_order_ids.state',
    )
    def _compute_progress(self):
        today = date.today()
        for rec in self:
            # ── Financial progress ────────────────────────────────
            boq_lines = rec.boq_ids
            total_contracted = sum(l.contracted_qty * l.unit_price for l in boq_lines)
            total_executed   = sum(l.executed_qty   * l.unit_price for l in boq_lines)
            rec.total_boq_value = total_contracted
            rec.financial_progress = (total_executed / total_contracted * 100) if total_contracted else 0.0

            # ── Certified amount ──────────────────────────────────
            approved_certs = rec.certificate_ids.filtered(lambda c: c.state == 'waqf_approved')
            rec.certified_amount = sum(approved_certs.mapped('certified_amount'))

            # ── Change orders ─────────────────────────────────────
            approved_co = rec.change_order_ids.filtered(lambda c: c.state == 'approved')
            rec.change_order_value = sum(approved_co.mapped('amount'))

            # ── Time progress ─────────────────────────────────────
            if rec.planned_start and rec.planned_end:
                total_days   = (rec.planned_end - rec.planned_start).days or 1
                elapsed_days = (today - rec.planned_start).days
                rec.time_progress = max(0.0, min(100.0, elapsed_days / total_days * 100))
                # Delay: if execution not done yet
                if today > rec.planned_end and rec.state not in ('final_hov', 'closed'):
                    rec.days_delay = (today - rec.planned_end).days
                else:
                    rec.days_delay = 0
            else:
                rec.time_progress = 0.0
                rec.days_delay = 0

            # ── Visit compliance ──────────────────────────────────
            if rec.planned_start and rec.state == 'active':
                weeks_elapsed = max(1, (today - rec.planned_start).days // 7)
                required_visits = weeks_elapsed * 2          # min 2/week per contract
                actual_visits   = len(rec.attendance_ids.filtered(
                    lambda a: a.is_validated and a.visit_type == 'field'))
                rec.visit_compliance = min(100.0, actual_visits / required_visits * 100)
            else:
                rec.visit_compliance = 100.0

            # ── Overall KPI ───────────────────────────────────────
            rec.overall_kpi = (
                rec.financial_progress * 0.40 +
                rec.time_progress      * 0.35 +
                rec.visit_compliance   * 0.25
            )

    @api.depends('overall_kpi')
    def _compute_kpi_color(self):
        for rec in self:
            if rec.overall_kpi >= 80:
                rec.kpi_color = 'success'
            elif rec.overall_kpi >= 60:
                rec.kpi_color = 'warning'
            else:
                rec.kpi_color = 'danger'

    @api.depends('boq_ids', 'certificate_ids', 'supervision_ids', 'change_order_ids')
    def _compute_counts(self):
        for rec in self:
            rec.boq_count          = len(rec.boq_ids)
            rec.certificate_count  = len(rec.certificate_ids)
            rec.supervision_count  = len(rec.supervision_ids)
            rec.change_order_count = len(rec.change_order_ids)

    # ── Actions ───────────────────────────────────────────────────
    def action_mobilize(self):
        self.write({'state': 'mobilizing'})

    def action_start(self):
        self.write({'state': 'active', 'actual_start': date.today()})

    def action_initial_handover(self):
        self.write({'state': 'initial_hov'})

    def action_final_handover(self):
        self.write({'state': 'final_hov', 'actual_end': date.today()})

    def action_warranty(self):
        self.write({'state': 'warranty'})

    def action_close(self):
        self.write({'state': 'closed'})

    def action_view_boq(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bill of Quantities — %s') % self.name,
            'res_model': 'mosque.boq',
            'view_mode': 'tree,form',
            'domain': [('mosque_id', '=', self.id)],
            'context': {'default_mosque_id': self.id},
        }

    def action_view_certificates(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment Certificates — %s') % self.name,
            'res_model': 'mosque.certificate',
            'view_mode': 'tree,form',
            'domain': [('mosque_id', '=', self.id)],
            'context': {'default_mosque_id': self.id},
        }
