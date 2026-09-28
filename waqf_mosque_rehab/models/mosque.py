from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import date, datetime, time, timedelta
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
    name = fields.Char(string='Mosque Name', required=True, tracking=True,translate=False)
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
                                          string='Payment value')
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
        'attendance_ids', 'attendance_ids.check_in', 'attendance_ids.duration',
        'planned_start', 'planned_end', 'state',
        'change_order_ids.amount', 'change_order_ids.state',
    )
    def _compute_progress(self):
        today = date.today()
        presence = self._compliant_attendance_days()
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
                if (today > rec.planned_end and rec.financial_progress < 100
                        and rec.state not in ('initial_hov', 'final_hov', 'warranty', 'closed')):
                    rec.days_delay = (today - rec.planned_end).days
                else:
                    rec.days_delay = 0
            else:
                rec.time_progress = 0.0
                rec.days_delay = 0

            # ── Visit compliance (الحضور اليومي) ──────────────────
            # مطلوب حضور يومي من الأحد إلى الخميس عدا الإجازات الرسمية.
            # اليوم يُحتسب للمسجد إذا حضر فيه مهندس وبلغ مجموع ساعاته في ذلك
            # اليوم 8 ساعات على كل المساجد (قد يمر المهندس على أكثر من مسجد).
            if rec.planned_start and rec.state == 'active':
                last_day = self._riyadh_today() - timedelta(days=1)   # اليوم الحالي لم يكتمل
                workdays = self._required_workdays(rec.planned_start, last_day)
                if workdays:
                    present = presence.get(rec.id, set()) & workdays
                    rec.visit_compliance = min(100.0, len(present) / len(workdays) * 100)
                else:
                    rec.visit_compliance = 100.0
            else:
                rec.visit_compliance = 100.0

            # ── Overall KPI (مؤشر الأداء العام) ───────────────────
            # المعادلة السابقة كانت تجمع التقدم الزمني كنقاط، فيرتفع المؤشر
            # بمرور الوقت حتى بدون إنجاز. المعادلة الحالية تقيس الأداء:
            #   60% الالتزام بالجدول = الإنجاز الفعلي ÷ المخطط (بهامش 5 نقاط لبداية المشروع)
            #   25% الالتزام بالحضور اليومي (8 ساعات، الأحد–الخميس)
            #   15% الالتزام بالمدة  = 100 − نقطتان لكل يوم تأخير
            # مشروع لم يبدأ ولا إنجاز فيه = 0 (يظهر «لم يبدأ»).
            done = rec.state in ('initial_hov', 'final_hov', 'warranty', 'closed')
            actual, planned = rec.financial_progress, rec.time_progress
            if not done and actual == 0 and planned == 0:
                rec.overall_kpi = 0.0
            else:
                schedule = 100.0 if done else min(100.0, (actual + 5.0) / (planned + 5.0) * 100.0)
                duration = max(0.0, 100.0 - rec.days_delay * 2.0)
                rec.overall_kpi = round(
                    schedule * 0.60 +
                    rec.visit_compliance * 0.25 +
                    duration * 0.15, 1)

    # ── Daily attendance helpers ──────────────────────────────────
    DAILY_HOURS = 8.0
    WORK_WEEKDAYS = (6, 0, 1, 2, 3)          # الأحد … الخميس (Python: الاثنين = 0)
    RIYADH_OFFSET = timedelta(hours=3)       # الرياض UTC+3 بدون توقيت صيفي

    @api.model
    def _riyadh_today(self):
        return (datetime.utcnow() + self.RIYADH_OFFSET).date()

    @api.model
    def _required_workdays(self, start, end):
        """أيام العمل المطلوبة بين تاريخين (شاملة) عدا الإجازات الرسمية."""
        if not start or not end or start > end:
            return set()
        holidays = self.env['mosque.public.holiday'].sudo()._holiday_dates(start, end)
        days, d = set(), start
        while d <= end:
            if d.weekday() in self.WORK_WEEKDAYS and d not in holidays:
                days.add(d)
            d += timedelta(days=1)
        return days

    def _compliant_attendance_days(self):
        """{mosque_id: {أيام بتوقيت الرياض}} الأيام التي حضر فيها مهندس للمسجد
        وبلغ مجموع ساعاته في ذلك اليوم (على كل المساجد) 8 ساعات."""
        mosques = self.filtered(lambda m: isinstance(m.id, int) and m.planned_start and m.state == 'active')
        if not mosques:
            return {}
        since = datetime.combine(min(mosques.mapped('planned_start')), time.min) - self.RIYADH_OFFSET
        Att = self.env['mosque.attendance'].sudo()

        def person(a):
            return ('e', a.engineer_id.id) if a.engineer_id else \
                   ('u', a.portal_user_id.id) if a.portal_user_id else None

        local = Att.search([('mosque_id', 'in', mosques.ids), ('check_in', '>=', since)])
        engineers = local.mapped('engineer_id').ids
        users = local.mapped('portal_user_id').ids
        if not engineers and not users:
            return {}
        # كل حضور هؤلاء المهندسين في كل المساجد لجمع ساعاتهم اليومية
        domain = [('check_in', '>=', since)]
        if engineers and users:
            domain += ['|', ('engineer_id', 'in', engineers), ('portal_user_id', 'in', users)]
        elif engineers:
            domain += [('engineer_id', 'in', engineers)]
        else:
            domain += [('portal_user_id', 'in', users)]
        totals = {}
        for a in Att.search(domain):
            key = person(a)
            if key:
                day = (a.check_in + self.RIYADH_OFFSET).date()
                totals[(key, day)] = totals.get((key, day), 0.0) + (a.duration or 0.0)

        result = {}
        for a in local:
            key = person(a)
            if not key:
                continue
            day = (a.check_in + self.RIYADH_OFFSET).date()
            if totals.get((key, day), 0.0) >= self.DAILY_HOURS - 0.01:
                result.setdefault(a.mosque_id.id, set()).add(day)
        return result

    # ── Daily refresh ─────────────────────────────────────────────
    def _recompute_progress(self):
        """التقدم الزمني والتأخير والمؤشر تعتمد على تاريخ اليوم، لكنها مخزّنة
        ولا تُعاد إلا عند تغيّر البيانات؛ هذه الدالة تُعيد حسابها الآن."""
        if not self:
            return
        # كل حقول _compute_progress تعتمد على planned_start، فإعلامها بتغيّره يعيد حسابها
        self.modified(['planned_start'])
        self.env.flush_all()

    @api.model
    def _cron_recompute_progress(self):
        self.search([('state', 'not in', ['closed'])])._recompute_progress()

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
            'view_mode': 'list,form',
            'domain': [('mosque_id', '=', self.id)],
            'context': {'default_mosque_id': self.id},
        }

    def action_view_certificates(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Payment Certificates — %s') % self.name,
            'res_model': 'mosque.certificate',
            'view_mode': 'list,form',
            'domain': [('mosque_id', '=', self.id)],
            'context': {'default_mosque_id': self.id},
        }
