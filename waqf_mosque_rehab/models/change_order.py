from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date


class MosqueChangeOrder(models.Model):
    _name = 'mosque.change.order'
    _description = 'Change Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    name = fields.Char(string='Reference', readonly=True, copy=False,
                       default=lambda self: _('New'))
    mosque_id    = fields.Many2one('mosque.mosque', string='Mosque',
                                   required=True, index=True)
    type = fields.Selection([
        ('scope',    'Scope Change'),
        ('design',   'Design Modification'),
        ('time',     'Time Extension'),
        ('cost',     'Cost Adjustment'),
    ], string='Type', required=True)
    reason = fields.Text(string='Reason / Justification', required=True)
    amount = fields.Monetary(string='Amount (SAR)', currency_field='currency_id')
    days_extension = fields.Integer(string='Days Extension')
    currency_id = fields.Many2one('res.currency',
                                  default=lambda s: s.env.ref('base.SAR'))
    state = fields.Selection([
        ('draft',    'Draft'),
        ('review',   'Under Review'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ], string='Status', default='draft', tracking=True)
    approved_by = fields.Many2one('res.users', string='Approved By', readonly=True)
    approved_date = fields.Date(string='Approved Date', readonly=True)
    boq_line_ids = fields.One2many('mosque.boq', 'change_order_id',
                                   string='BOQ Variation Items')

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code('mosque.change.order')
        return super().create(vals_list)

    def action_submit(self):
        self.write({'state': 'review'})

    def action_approve(self):
        self.write({
            'state': 'approved',
            'approved_by': self.env.user.id,
            'approved_date': date.today(),
        })
        # Extend planned end if time extension
        for rec in self:
            if rec.days_extension and rec.mosque_id.planned_end:
                from datetime import timedelta
                new_end = rec.mosque_id.planned_end + timedelta(days=rec.days_extension)
                rec.mosque_id.planned_end = new_end

    def action_reject(self):
        self.write({'state': 'rejected'})


class MosqueAttendance(models.Model):
    _name = 'mosque.attendance'
    _description = 'Field Visit Attendance Log'
    _order = 'check_in desc'

    name = fields.Char(
        string='Name',
        compute='_compute_name',
        store=True
    )

    mosque_id   = fields.Many2one('mosque.mosque', string='Mosque',
                                  required=True, index=True)
    # في MosqueAttendance model
    portal_user_id = fields.Many2one(
        'res.users',
        string='مستخدم البوابة',
    )

    # عدّل engineer_id ليكون غير مطلوب
    engineer_id = fields.Many2one(
        'hr.employee',
        string='Engineer',
        required=False,  # ← غيّر من True إلى False
    )
    visit_type  = fields.Selection([
        ('field',        'Field Visit'),
        ('pre_closure',  'Pre-Closure Inspection'),
        ('pre_testing',  'Pre-Testing & Commissioning'),
        ('handover',     'Initial Handover'),
        ('itp',          'ITP Hold Point'),
        ('emergency',    'Emergency Response'),
    ], string='Visit Type', required=True, default='field')

    check_in  = fields.Datetime(string='Check-In',  required=True)
    check_out = fields.Datetime(string='Check-Out')
    duration  = fields.Float(string='Duration (hrs)', compute='_compute_duration',
                             store=True, digits=(5, 2))

    # GPS & QR validation
    gps_latitude  = fields.Float(string='GPS Lat',  digits=(10, 7))
    gps_longitude = fields.Float(string='GPS Lon',  digits=(10, 7))
    gps_validated = fields.Boolean(string='GPS Validated', default=False)
    qr_validated  = fields.Boolean(string='QR Validated',  default=False)
    distance_m    = fields.Float(string='Distance (m)')

    is_validated = fields.Boolean(string='Validated Visit',
                                  compute='_compute_validated', store=True)

    # Media
    checkin_photo  = fields.Binary(string='Check-In Photo')
    checkout_photo = fields.Binary(string='Check-Out Photo')
    live_stream_url= fields.Char(string='Live Stream URL')
    notes = fields.Text(string='Visit Notes')

    # API token for mobile app
    mobile_token = fields.Char(string='Mobile Session Token', copy=False)

    @api.depends('mosque_id', 'engineer_id', 'portal_user_id', 'visit_type', 'check_in')
    def _compute_name(self):
        for rec in self:
            person = rec.engineer_id.name or rec.portal_user_id.name or ''
            date_str = rec.check_in.strftime('%Y-%m-%d %H:%M') if rec.check_in else ''
            rec.name = f'{rec.mosque_id.name or ""} - {person}'

    @api.depends('check_in', 'check_out')
    def _compute_duration(self):
        for rec in self:
            if rec.check_in and rec.check_out:
                delta = rec.check_out - rec.check_in
                rec.duration = delta.total_seconds() / 3600
            else:
                rec.duration = 0.0

    @api.depends('gps_validated', 'qr_validated', 'distance_m', 'mosque_id.geofence_radius')
    def _compute_validated(self):
        for rec in self:
            within_fence = rec.distance_m <= (rec.mosque_id.geofence_radius or 100)
            rec.is_validated = rec.qr_validated and within_fence

    @api.model
    def register_visit_from_mobile(self, payload):
        """
        Called from mobile app via JSON-RPC.
        payload: {
            mosque_code, engineer_id, gps_lat, gps_lon,
            qr_token, check_in, photo_base64, visit_type
        }
        Returns: {success, attendance_id, is_validated, distance_m}
        """
        import math
        mosque = self.env['mosque.mosque'].search(
            [('code', '=', payload.get('mosque_code'))], limit=1)
        if not mosque:
            return {'success': False, 'error': 'Mosque not found'}

        qr_ok = mosque.qr_code == payload.get('qr_token')

        # Haversine distance
        lat1 = math.radians(payload.get('gps_lat', 0))
        lon1 = math.radians(payload.get('gps_lon', 0))
        lat2 = math.radians(mosque.latitude)
        lon2 = math.radians(mosque.longitude)
        dlat, dlon = lat2-lat1, lon2-lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
        distance = 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

        attendance = self.create({
            'mosque_id':    mosque.id,
            'engineer_id':  payload.get('engineer_id'),
            'visit_type':   payload.get('visit_type', 'field'),
            'check_in':     payload.get('check_in'),
            'gps_latitude': payload.get('gps_lat'),
            'gps_longitude':payload.get('gps_lon'),
            'gps_validated':True,
            'qr_validated': qr_ok,
            'distance_m':   round(distance, 1),
        })

        return {
            'success':      True,
            'attendance_id':attendance.id,
            'is_validated': attendance.is_validated,
            'distance_m':   round(distance, 1),
            'qr_ok':        qr_ok,
        }
