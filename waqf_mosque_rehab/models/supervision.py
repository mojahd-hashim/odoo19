from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date, timedelta


class MosqueSupervision(models.Model):
    _name = 'mosque.supervision'
    _description = 'Supervision Report'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'report_date desc'

    name = fields.Char(string='Reference', readonly=True, copy=False,
                       default=lambda self: _('New'))
    mosque_id   = fields.Many2one('mosque.mosque', string='Mosque',
                                  required=True, index=True)
    engineer_id = fields.Many2one(
        'res.users',
        string='User',
        required=True,
        default=lambda self: self.env.user
    )
    report_date = fields.Date(string='Report Date', required=True,
                              default=fields.Date.today)
    report_type = fields.Selection([
        ('daily',   'Daily Site Report'),
        ('weekly',  'Weekly Quality Report'),
        ('monthly', 'Monthly Progress Report'),
        ('itp',     'ITP Inspection'),
        ('hse',     'HSE Safety Report'),
        ('handover','Handover Inspection'),
    ], string='Report Type', required=True, default='daily')

    state = fields.Selection([
        ('draft',    'Draft'),
        ('submitted','Submitted'),
        ('approved', 'Approved'),
    ], string='Status', default='draft', tracking=True)

    # ── Site Conditions ────────────────────────────────────────────
    weather = fields.Selection([
        ('sunny', 'Sunny'), ('cloudy', 'Cloudy'),
        ('windy', 'Windy'), ('rainy', 'Rainy'),
    ], string='Weather', default='sunny')
    workers_on_site = fields.Integer(string='Workers on Site')
    equipment_count = fields.Integer(string='Equipment Count')

    # ── Activities ────────────────────────────────────────────────
    activities_done = fields.Text(string='Activities Completed')
    activities_planned = fields.Text(string='Activities Planned (Next Period)')
    issues = fields.Text(string='Issues & Obstacles')
    recommendations = fields.Text(string='Recommendations')

    # ── Quality & Safety ──────────────────────────────────────────
    ncr_count = fields.Integer(string='Non-Conformance Reports (NCR)')
    safety_incidents = fields.Integer(string='Safety Incidents', default=0)
    itp_hold_points_checked = fields.Integer(string='ITP Hold Points Checked')
    itp_hold_points_approved = fields.Integer(string='ITP Hold Points Approved')

    # ── Progress update ────────────────────────────────────────────
    boq_progress_ids = fields.One2many('mosque.supervision.boq', 'supervision_id',
                                       string='BOQ Progress Update')

    # ── Media ─────────────────────────────────────────────────────
    photo_ids = fields.Many2many('ir.attachment', string='Site Photos',
                                 domain=[('mimetype', 'like', 'image')])
    photo_360_url = fields.Char(string='رابط صورة 360°')
    live_stream_url = fields.Char(string='Live Stream URL')
    video_report_url = fields.Char(string='Video Report URL')

    # ── Validation (GPS/QR from mobile) ──────────────────────────
    gps_latitude    = fields.Float(string='GPS Latitude',  digits=(10, 7))
    gps_longitude   = fields.Float(string='GPS Longitude', digits=(10, 7))
    gps_validated   = fields.Boolean(string='GPS Validated', default=False)
    qr_validated    = fields.Boolean(string='QR Validated',  default=False)
    distance_to_site = fields.Float(string='Distance to Site (m)',
                                    compute='_compute_distance', store=True)
    is_within_geofence = fields.Boolean(string='Within Geofence',
                                        compute='_compute_distance', store=True)

    # ── Quality & Safety ──────────────────────────────────────────
    workforce_ids = fields.One2many(
        'mosque.supervision.workforce', 'supervision_id',
        string='بيان العمالة والمعدات')

    manpower_count = fields.Integer(
        string='إجمالي العمالة',
        compute='_compute_workforce_totals', store=True)
    equipment_count_total = fields.Integer(
        string='إجمالي المعدات',
        compute='_compute_workforce_totals', store=True)

    @api.depends('workforce_ids.count', 'workforce_ids.category')
    def _compute_workforce_totals(self):
        for rec in self:
            lines = rec.workforce_ids
            rec.manpower_count = sum(
                l.count for l in lines if l.category == 'manpower')
            rec.equipment_count_total = sum(
                l.count for l in lines if l.category == 'equipment')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('mosque.supervision') or _('New')
        return super().create(vals_list)

    @api.depends('gps_latitude', 'gps_longitude', 'mosque_id.latitude', 'mosque_id.longitude')
    def _compute_distance(self):
        import math
        for rec in self:
            m = rec.mosque_id
            if all([rec.gps_latitude, rec.gps_longitude, m.latitude, m.longitude]):
                # Haversine formula
                R = 6371000
                lat1, lon1 = math.radians(rec.gps_latitude), math.radians(rec.gps_longitude)
                lat2, lon2 = math.radians(m.latitude), math.radians(m.longitude)
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
                rec.distance_to_site = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
                rec.is_within_geofence = rec.distance_to_site <= (m.geofence_radius or 100)
            else:
                rec.distance_to_site = 0.0
                rec.is_within_geofence = False

    def action_submit(self):
        for rec in self:
            if not rec.activities_done:
                raise ValidationError(_('Please fill in the activities completed section.'))
        self.write({'state': 'submitted'})

    def action_approve(self):
        self.write({'state': 'approved'})

    def action_reset(self):
        self.write({'state': 'draft'})


class MosqueSupervisionBOQ(models.Model):
    _name = 'mosque.supervision.boq'
    _description = 'Supervision BOQ Progress Line'

    supervision_id = fields.Many2one('mosque.supervision', ondelete='cascade')
    boq_id = fields.Many2one('mosque.boq', string='BOQ Item', required=True)
    description = fields.Text(related='boq_id.description', readonly=True)
    previous_qty = fields.Float(string='Previous Qty', digits=(12, 3),
                                related='boq_id.executed_qty', readonly=True)
    this_period_qty = fields.Float(string='This Period Qty', digits=(12, 3))
    cumulative_qty  = fields.Float(string='Cumulative Qty', digits=(12, 3),
                                   compute='_compute_cumulative', store=True)
    progress_pct    = fields.Float(string='Progress %', digits=(5, 2),
                                   compute='_compute_cumulative', store=True)
    remarks = fields.Char(string='Remarks')

    @api.depends('previous_qty', 'this_period_qty', 'boq_id.contracted_qty')
    def _compute_cumulative(self):
        for rec in self:
            rec.cumulative_qty = rec.previous_qty + rec.this_period_qty
            if rec.boq_id.contracted_qty:
                rec.progress_pct = min(100.0,
                    rec.cumulative_qty / rec.boq_id.contracted_qty * 100)
            else:
                rec.progress_pct = 0.0

class MosqueWorkforceType(models.Model):
    _name = 'mosque.workforce.type'
    _description = 'نوع العمالة أو المعدة'
    _order = 'category, sequence'

    name     = fields.Char(string='الاسم', required=True)
    category = fields.Selection([
        ('manpower',  'عمالة'),
        ('equipment', 'معدات'),
    ], string='التصنيف', required=True, default='manpower')
    sequence = fields.Integer(default=10)
    active   = fields.Boolean(default=True)


class MosqueSupervisionWorkforce(models.Model):
    _name = 'mosque.supervision.workforce'
    _description = 'بيان العمالة والمعدات'
    _order = 'sequence'

    supervision_id = fields.Many2one(
        'mosque.supervision', required=True, ondelete='cascade')
    type_id  = fields.Many2one(
        'mosque.workforce.type', string='جهاز المقاول',
        required=True)
    category = fields.Selection(
        related='type_id.category', readonly=True, store=True)
    count    = fields.Integer(string='العدد', default=0)
    sequence = fields.Integer(default=10)