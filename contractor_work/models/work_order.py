# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import date, timedelta


class ContractorWorkOrder(models.Model):
    """
    سجل أمر العمل الرئيسي — يحتوي على كامل دورة حياة العمل:
    البدء → التسليم → الاختبار → الضمان
    """
    _name        = 'contractor.work.order'
    _description = 'أمر عمل المقاول'
    _inherit     = ['mail.thread', 'mail.activity.mixin']
    _order       = 'mosque_id, date_requested desc'

    # ── Identity ───────────────────────────────────────────────
    name = fields.Char(
        string='رقم الأمر', readonly=True,
        copy=False, default='جديد')

    mosque_id = fields.Many2one(
        'mosque.mosque', string='المسجد',
        required=True, index=True, tracking=True)

    task_id = fields.Many2one(
        'project.task', string='المهمة الرئيسية',
        domain="[('parent_id','=',False)]",
        tracking=True)

    supervisor_id = fields.Many2one(
        'res.partner', string='المشرف / المقاول',
        required=True, tracking=True)

    portal_user_id = fields.Many2one(
        'res.users', string='مستخدم البوابة')

    work_description = fields.Text(
        string='وصف العمل', required=True)

    # ── State ──────────────────────────────────────────────────
    state = fields.Selection([
        ('draft',        'مسودة'),
        ('submitted',    'بانتظار اعتماد البدء'),
        ('approved',     'معتمد — قيد التنفيذ'),
        ('delivered',    'مسلّم — بانتظار التقييم'),
        ('graded',       'تم التقييم'),
        ('rework',       'إعادة عمل'),
        ('testing',      'قيد الاختبار'),
        ('warranty',     'فترة الضمان'),
        ('closed',       'مغلق'),
        ('rejected',     'مرفوض'),
    ], string='الحالة', default='draft',
       tracking=True, index=True)

    # ── Phase 1: Commencement ──────────────────────────────────
    date_requested     = fields.Date(string='تاريخ الطلب', default=fields.Date.today)
    date_planned_start = fields.Date(string='تاريخ البدء المخطط')
    date_planned_end   = fields.Date(string='تاريخ الإنجاز المخطط')

    qualification_id = fields.Many2one(
        'contractor.qualification',
        string='تأهيل المقاول',
        domain="[('supervisor_id','=',supervisor_id),('state','=','approved')]",
        help='مطلوب لأعمال متخصصة فقط')

    boq_line_ids = fields.One2many(
        'contractor.work.order.boq', 'work_order_id',
        string='بنود جدول الكميات')

    site_photo_ids = fields.Many2many(
        'ir.attachment',
        'work_order_site_photos_rel',
        'work_order_id', 'attachment_id',
        string='صور الموقع (قبل البدء)',
        domain=[('mimetype', 'like', 'image')])

    commencement_notes = fields.Text(string='ملاحظات طلب البدء')

    # اعتماد البدء
    commencement_approved_by = fields.Many2one(
        'res.users', string='اعتمد البدء', readonly=True)
    commencement_approval_date = fields.Date(
        string='تاريخ اعتماد البدء', readonly=True)
    commencement_reject_reason = fields.Text(
        string='سبب رفض البدء')

    # ── Phase 2: Delivery ──────────────────────────────────────
    date_delivered = fields.Date(string='تاريخ التسليم')

    delivery_photo_ids = fields.Many2many(
        'ir.attachment',
        'work_order_delivery_photos_rel',
        'work_order_id', 'attachment_id',
        string='صور إثبات التسليم',
        domain=[('mimetype', 'like', 'image')])

    delivery_notes = fields.Text(string='ملاحظات التسليم')

    # تقييم ABCD
    grade = fields.Selection([
        ('a', 'A — مقبول'),
        ('b', 'B — مقبول مع ملاحظات'),
        ('c', 'C — إعادة عمل جزئي'),
        ('d', 'D — مرفوض'),
    ], string='التقييم', tracking=True)

    grade_notes = fields.Text(string='ملاحظات التقييم')

    graded_by   = fields.Many2one('res.users', string='قيّم بواسطة', readonly=True)
    grade_date  = fields.Date(string='تاريخ التقييم', readonly=True)

    payment_pct = fields.Float(
        string='نسبة الدفع %',
        compute='_compute_payment_pct', store=True)

    # سجل إعادة العمل
    rework_log_ids = fields.One2many(
        'contractor.work.order.rework', 'work_order_id',
        string='سجل إعادة العمل')

    rework_count = fields.Integer(
        compute='_compute_rework_count', string='عدد مرات الإعادة')

    # ── Phase 3: Testing ───────────────────────────────────────
    test_ids = fields.One2many(
        'contractor.work.order.test', 'work_order_id',
        string='الاختبارات')

    test_count  = fields.Integer(compute='_compute_counts', string='الاختبارات')
    tests_passed = fields.Boolean(
        compute='_compute_counts', string='اجتازت الاختبارات', store=True)

    # ── Phase 4: Warranty ──────────────────────────────────────
    warranty_ids = fields.One2many(
        'contractor.work.order.warranty', 'work_order_id',
        string='الضمانات')

    warranty_count = fields.Integer(compute='_compute_counts', string='الضمانات')

    # ── Material Submittals ────────────────────────────────────
    submittal_ids = fields.One2many(
        'contractor.material.submittal', 'work_order_id',
        string='عينات المواد')

    submittal_count = fields.Integer(
        compute='_compute_counts', string='العينات')

    # ── Computed ───────────────────────────────────────────────
    total_value = fields.Float(
        string='إجمالي القيمة',
        compute='_compute_totals', store=True, digits=(16, 2))

    total_qty_lines = fields.Integer(
        compute='_compute_totals', string='عدد البنود')

    @api.depends('boq_line_ids.line_value')
    def _compute_totals(self):
        for rec in self:
            rec.total_value     = sum(rec.boq_line_ids.mapped('line_value'))
            rec.total_qty_lines = len(rec.boq_line_ids)

    @api.depends('grade')
    def _compute_payment_pct(self):
        ICP = self.env['ir.config_parameter'].sudo()
        pct = {
            'a': float(ICP.get_param('contractor.grade_a_pct', 100)),
            'b': float(ICP.get_param('contractor.grade_b_pct', 100)),
            'c': float(ICP.get_param('contractor.grade_c_pct', 0)),
            'd': float(ICP.get_param('contractor.grade_d_pct', 0)),
        }
        for rec in self:
            rec.payment_pct = pct.get(rec.grade, 0) if rec.grade else 0

    @api.depends('rework_log_ids')
    def _compute_rework_count(self):
        for rec in self:
            rec.rework_count = len(rec.rework_log_ids)

    @api.depends('test_ids', 'warranty_ids', 'submittal_ids')
    def _compute_counts(self):
        for rec in self:
            rec.test_count     = len(rec.test_ids)
            rec.warranty_count = len(rec.warranty_ids)
            rec.submittal_count= len(rec.submittal_ids)
            rec.tests_passed   = bool(rec.test_ids) and all(
                t.result == 'pass' for t in rec.test_ids)

    # ── Sequence ───────────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'جديد') == 'جديد':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'contractor.work.order') or 'جديد'
        return super().create(vals_list)

    # ── Actions / Workflow ─────────────────────────────────────
    def action_submit_commencement(self):
        """إرسال طلب البدء للاستشاري."""
        for rec in self:
            if not rec.boq_line_ids:
                raise UserError('يجب إضافة بند واحد على الأقل من جدول الكميات.')
            # تحقق من العينات المطلوبة
            for line in rec.boq_line_ids:
                if line.boq_id.requires_sample:
                    approved_sub = rec.submittal_ids.filtered(
                        lambda s: s.boq_id == line.boq_id
                        and s.state == 'approved')
                    if not approved_sub:
                        raise UserError(
                            f'البند "{line.boq_id.description}" يتطلب اعتماد عينة أولاً.')
            # تحقق من التأهيل إذا لزم
            for line in rec.boq_line_ids:
                if line.boq_id.requires_qualification and not rec.qualification_id:
                    raise UserError(
                        f'البند "{line.boq_id.description}" يتطلب تأهيل مقاول معتمد.')
            rec.write({'state': 'submitted'})
            rec.message_post(body='📋 تم إرسال طلب البدء للاستشاري')

    def action_approve_commencement(self):
        """الاستشاري يعتمد البدء."""
        for rec in self:
            rec.write({
                'state': 'approved',
                'commencement_approved_by':   self.env.user.id,
                'commencement_approval_date': date.today(),
            })
            rec.message_post(
                body=f'✅ اعتمد البدء: {self.env.user.name}')

    def action_reject_commencement(self):
        """الاستشاري يرفض طلب البدء."""
        for rec in self:
            rec.write({'state': 'draft'})
            rec.message_post(
                body=f'❌ رُفض طلب البدء: {rec.commencement_reject_reason or ""}')

    def action_submit_delivery(self):
        """المقاول يرفع التسليم."""
        for rec in self:
            if not rec.delivery_photo_ids:
                raise UserError('يجب رفع صورة إثبات واحدة على الأقل.')
            rec.write({
                'state':          'delivered',
                'date_delivered': date.today(),
            })
            rec.message_post(body='🏗 تم إرسال التسليم للتقييم')

    def action_grade(self, grade, notes=''):
        """الاستشاري يقيّم التسليم."""
        for rec in self:
            next_state = {
                'a': 'graded',
                'b': 'graded',
                'c': 'rework',
                'd': 'rework',
            }.get(grade, 'graded')

            rec.write({
                'grade':      grade,
                'grade_notes': notes,
                'graded_by':  self.env.user.id,
                'grade_date': date.today(),
                'state':      next_state,
            })

            if grade in ('c', 'd'):
                rec.env['contractor.work.order.rework'].create({
                    'work_order_id': rec.id,
                    'grade':         grade,
                    'notes':         notes,
                    'date':          date.today(),
                })
                rec.message_post(
                    body=f'⚠ التقييم {grade.upper()} — مطلوب إعادة عمل')
            else:
                rec.message_post(
                    body=f'✅ التقييم {grade.upper()} — {notes}')

    def action_start_testing(self):
        """الانتقال لمرحلة الاختبار."""
        self.write({'state': 'testing'})

    def action_close(self):
        """إغلاق أمر العمل."""
        for rec in self:
            if rec.warranty_ids:
                rec.write({'state': 'warranty'})
            else:
                rec.write({'state': 'closed'})
            rec.message_post(body='🏁 تم إغلاق أمر العمل')

    def action_view_task(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'res_model': 'project.task',
            'res_id':    self.task_id.id,
            'view_mode': 'form',
        }


class ContractorWorkOrderBOQ(models.Model):
    """بنود BOQ المختارة في أمر العمل."""
    _name        = 'contractor.work.order.boq'
    _description = 'بند BOQ في أمر العمل'
    _order       = 'sequence'

    work_order_id = fields.Many2one(
        'contractor.work.order', required=True, ondelete='cascade')

    mosque_id = fields.Many2one(
        related='work_order_id.mosque_id', store=True)

    boq_id = fields.Many2one(
        'mosque.boq', string='البند',
        required=True,
        domain="[('mosque_id','=',mosque_id)]")

    description   = fields.Text(related='boq_id.description', readonly=True)
    item_code     = fields.Char(related='boq_id.item_code', readonly=True)
    uom           = fields.Selection(related='boq_id.uom', readonly=True)
    unit_price    = fields.Float(related='boq_id.unit_price', readonly=True)
    contracted_qty= fields.Float(related='boq_id.contracted_qty', readonly=True)
    remaining_qty = fields.Float(related='boq_id.remaining_qty', readonly=True)

    qty_requested = fields.Float(
        string='الكمية المطلوبة', required=True, digits=(12, 3))

    line_value = fields.Float(
        string='القيمة', compute='_compute_value', store=True, digits=(16, 2))

    sequence = fields.Integer(default=10)

    requires_sample        = fields.Boolean(related='boq_id.requires_sample', readonly=True)
    requires_qualification = fields.Boolean(related='boq_id.requires_qualification', readonly=True)

    @api.depends('qty_requested', 'unit_price')
    def _compute_value(self):
        for rec in self:
            rec.line_value = rec.qty_requested * rec.unit_price

    @api.constrains('qty_requested')
    def _check_qty(self):
        for rec in self:
            if rec.qty_requested <= 0:
                raise ValidationError('الكمية يجب أن تكون أكبر من صفر.')
            if rec.qty_requested > rec.remaining_qty:
                raise ValidationError(
                    f'الكمية المطلوبة ({rec.qty_requested}) تتجاوز '
                    f'المتبقي ({rec.remaining_qty}) للبند: {rec.boq_id.description}')


class ContractorWorkOrderRework(models.Model):
    """سجل إعادة العمل — مرتبط بنفس أمر العمل."""
    _name        = 'contractor.work.order.rework'
    _description = 'سجل إعادة العمل'
    _order       = 'date desc'

    work_order_id = fields.Many2one(
        'contractor.work.order', required=True, ondelete='cascade')

    date  = fields.Date(string='التاريخ', default=fields.Date.today)
    grade = fields.Selection([
        ('c', 'C — إعادة جزئي'),
        ('d', 'D — مرفوض'),
    ], string='التقييم')
    notes         = fields.Text(string='الملاحظات')
    resolved_date = fields.Date(string='تاريخ الحل')
    resolved      = fields.Boolean(string='تم الحل', default=False)

    photo_ids = fields.Many2many(
        'ir.attachment',
        'rework_photos_rel', 'rework_id', 'attachment_id',
        string='صور بعد الإصلاح',
        domain=[('mimetype', 'like', 'image')])


class ContractorWorkOrderTest(models.Model):
    """اختبارات أمر العمل."""
    _name        = 'contractor.work.order.test'
    _description = 'اختبار أمر العمل'
    _order       = 'date desc'

    work_order_id = fields.Many2one(
        'contractor.work.order', required=True, ondelete='cascade')

    name = fields.Char(string='نوع الاختبار', required=True)
    test_type = fields.Selection([
        ('insulation',   'عزل كهربائي'),
        ('pressure',     'اختبار ضغط'),
        ('commissioning','تشغيل وضبط'),
        ('fire',         'إنذار حريق'),
        ('water',        'اختبار تسرب مياه'),
        ('other',        'أخرى'),
    ], string='نوع الاختبار', required=True)

    date           = fields.Date(string='تاريخ الاختبار', default=fields.Date.today)
    result         = fields.Selection([
        ('pass', 'ناجح ✅'),
        ('fail', 'فاشل ❌'),
    ], string='النتيجة', tracking=True)

    tested_by      = fields.Many2one('res.users', string='نفّذ بواسطة')
    notes          = fields.Text(string='ملاحظات')
    certificate_id = fields.Many2one(
        'ir.attachment', string='شهادة الاختبار')

    retry_count    = fields.Integer(string='عدد المحاولات', default=0)


class ContractorWorkOrderWarranty(models.Model):
    """ضمانات أمر العمل."""
    _name        = 'contractor.work.order.warranty'
    _description = 'ضمان أمر العمل'
    _order       = 'date_start'

    work_order_id = fields.Many2one(
        'contractor.work.order', required=True, ondelete='cascade')

    name           = fields.Char(string='وصف الضمان', required=True)
    warranty_type  = fields.Selection([
        ('workmanship', 'ضمان تنفيذ'),
        ('material',    'ضمان مواد'),
        ('equipment',   'ضمان معدات'),
        ('other',       'أخرى'),
    ], string='نوع الضمان', required=True, default='workmanship')

    date_start     = fields.Date(string='تاريخ البدء', required=True)
    date_end       = fields.Date(string='تاريخ الانتهاء', required=True)
    duration_months= fields.Integer(string='مدة الضمان (شهر)')

    status = fields.Selection([
        ('active',  'ساري'),
        ('expired', 'منتهي'),
        ('claimed', 'تم المطالبة'),
    ], string='الحالة', compute='_compute_status', store=True)

    alert_days     = fields.Integer(string='التنبيه قبل (يوم)', default=30)
    notes          = fields.Text(string='ملاحظات')

    supplier_name  = fields.Char(string='المورد / المصنع')
    serial_number  = fields.Char(string='الرقم التسلسلي')
    certificate_id = fields.Many2one('ir.attachment', string='وثيقة الضمان')

    @api.depends('date_end')
    def _compute_status(self):
        today = date.today()
        for rec in self:
            if not rec.date_end:
                rec.status = 'active'
            elif rec.date_end < today:
                rec.status = 'expired'
            else:
                rec.status = 'active'

    @api.onchange('date_start', 'duration_months')
    def _onchange_duration(self):
        if self.date_start and self.duration_months:
            from dateutil.relativedelta import relativedelta
            self.date_end = self.date_start + relativedelta(
                months=self.duration_months)
