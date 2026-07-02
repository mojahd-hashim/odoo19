from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ContractorQualification(models.Model):
    """تأهيل المقاول لأعمال متخصصة — مع تقييم ABCD ودورة ثلاثية."""
    _name        = 'contractor.qualification'
    _description = 'تأهيل المقاول'
    _inherit     = ['mail.thread', 'mail.activity.mixin']
    _order       = 'date_requested desc'

    name = fields.Char(
        string='رقم التأهيل', readonly=True,
        copy=False, default='جديد')

    supervisor_id = fields.Many2one(
        'res.partner', string='المقاول / المشرف',
        required=True, tracking=True)

    work_category_id = fields.Many2one(
        'mosque.boq.category', string='نوع العمل',
        required=True,
        help='نوع العمل الذي يتقدم للتأهيل فيه')

    # ── النطاق ─────────────────────────────────────────────
    scope = fields.Selection([
        ('all',      'كل المساجد'),
        ('specific', 'مساجد محددة'),
    ], string='النطاق', default='all', required=True)

    mosque_ids = fields.Many2many(
        'mosque.mosque', string='المساجد المحددة',
        help='يُترك فارغاً للتأهيل العام')

    # ── الوثائق ────────────────────────────────────────────
    document_ids = fields.Many2many(
        'ir.attachment',
        'qualification_docs_rel', 'qual_id', 'att_id',
        string='الوثائق والشهادات')

    description    = fields.Text(string='وصف الكفاءة')
    date_requested = fields.Date(
        string='تاريخ الطلب', default=fields.Date.today)

    # ══════════════════════════════════════════════════════════
    #  دورة الحالة — ثلاث مراحل اعتماد
    # ══════════════════════════════════════════════════════════
    state = fields.Selection([
        ('draft',            'مسودة'),
        ('submitted',        'بانتظار المهندس المسؤول'),
        ('engineer_done',    'أنهى المهندس — بانتظار كبير المهندسين'),
        ('senior_done',      'أنهى كبير المهندسين — بانتظار الوقف'),
        ('approved',         'معتمد نهائياً ✅'),
        ('rejected',         'مرفوض ❌'),
    ], string='الحالة', default='draft', tracking=True, index=True)

    # ══════════════════════════════════════════════════════════
    #  التقييم ABCD — لكل مرحلة
    # ══════════════════════════════════════════════════════════
    GRADE_SELECTION = [
        ('a', 'A — مستوفي الشروط بالكامل'),
        ('b', 'B — مقبول مع ملاحظات'),
        ('c', 'C — مرفوض مع امكانية التعديل وإعادة الارسال'),
        ('d', 'D — غير مقبول'),
    ]

    # ── المهندس المسؤول ───────────────────────────────────
    engineer_grade = fields.Selection(
        GRADE_SELECTION, string='تقييم المهندس المسؤول', tracking=True)
    engineer_notes = fields.Text(
        string='ملاحظات المهندس المسؤول')
    engineer_by = fields.Many2one(
        'res.users', string='المهندس المسؤول', readonly=True)
    engineer_date = fields.Date(
        string='تاريخ تقييم المهندس', readonly=True)

    # ── كبير المهندسين ────────────────────────────────────
    senior_grade = fields.Selection(
        GRADE_SELECTION, string='تقييم كبير المهندسين', tracking=True)
    senior_notes = fields.Text(
        string='ملاحظات كبير المهندسين')
    senior_by = fields.Many2one(
        'res.users', string='كبير المهندسين', readonly=True)
    senior_date = fields.Date(
        string='تاريخ تقييم كبير المهندسين', readonly=True)

    # ── الوقف (الاعتماد النهائي) ──────────────────────────
    waqf_grade = fields.Selection(
        GRADE_SELECTION, string='تقييم الوقف', tracking=True)
    waqf_notes = fields.Text(
        string='ملاحظات الوقف')
    waqf_by = fields.Many2one(
        'res.users', string='معتمد الوقف', readonly=True)
    waqf_date = fields.Date(
        string='تاريخ اعتماد الوقف', readonly=True)

    # ── سبب الرفض العام ───────────────────────────────────
    reject_reason = fields.Text(string='سبب الرفض')
    notes = fields.Text(string='ملاحظات عامة')

    # ── التقييم النهائي (محسوب) ────────────────────────────
    final_grade = fields.Selection(
        GRADE_SELECTION, string='التقييم النهائي',
        compute='_compute_final_grade', store=True)

    @api.depends('engineer_grade', 'senior_grade', 'waqf_grade')
    def _compute_final_grade(self):
        """التقييم النهائي = أسوأ تقييم بين المراحل الثلاث."""
        rank = {'a': 0, 'b': 1, 'c': 2, 'd': 3}
        rev  = {0: 'a', 1: 'b', 2: 'c', 3: 'd'}
        for rec in self:
            grades = [g for g in [
                rec.engineer_grade, rec.senior_grade, rec.waqf_grade
            ] if g]
            if grades:
                worst = max(rank.get(g, 0) for g in grades)
                rec.final_grade = rev[worst]
            else:
                rec.final_grade = False

    # ══════════════════════════════════════════════════════════
    #  Sequence
    # ══════════════════════════════════════════════════════════
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'جديد') == 'جديد':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'contractor.qualification') or 'جديد'
        return super().create(vals_list)

    # ══════════════════════════════════════════════════════════
    #  دالة مساعدة للتحقق من التقييم
    # ══════════════════════════════════════════════════════════
    def _validate_grade(self, grade, notes, stage_name):
        """B/C/D يلزم ملاحظات."""
        if not grade:
            raise UserError(_('يرجى اختيار التقييم (A/B/C/D) قبل الاعتماد.'))
        if grade in ('b', 'c', 'd') and not (notes or '').strip():
            raise UserError(
                _('التقييم %s يتطلب كتابة الملاحظات / السبب في خانة "%s".')
                % (grade.upper(), stage_name))

    # ══════════════════════════════════════════════════════════
    #  Actions — دورة العمل
    # ══════════════════════════════════════════════════════════

    # ── المقاول يرسل الطلب ────────────────────────────────
    def action_submit(self):
        for rec in self:
            rec.write({'state': 'submitted'})
            rec.message_post(body=_('📋 تم إرسال طلب التأهيل للمهندس المسؤول'))

    # ── المهندس المسؤول يقيّم ─────────────────────────────
    def action_engineer_approve(self):
        for rec in self:
            rec._validate_grade(
                rec.engineer_grade, rec.engineer_notes,
                'ملاحظات المهندس المسؤول')

            if rec.engineer_grade in  ['c','d']:
                # D → رفض مباشر
                rec.write({
                    'state':         'rejected',
                    'reject_reason': rec.engineer_notes,
                    'engineer_by':   self.env.user.id,
                    'engineer_date': fields.Date.today(),
                })
                rec.message_post(
                    body=_('❌ المهندس المسؤول رفض — تقييم D: %s')
                    % rec.engineer_notes)
            else:
                rec.write({
                    'state':         'engineer_done',
                    'engineer_by':   self.env.user.id,
                    'engineer_date': fields.Date.today(),
                })
                rec.message_post(
                    body=_('✅ المهندس المسؤول — تقييم %s%s')
                    % (rec.engineer_grade.upper(),
                       ': ' + rec.engineer_notes if rec.engineer_notes else ''))

    # ── كبير المهندسين يقيّم ──────────────────────────────
    def action_senior_approve(self):
        for rec in self:
            rec.write({
                'state':       'senior_done',
                'senior_by':   self.env.user.id,
                'senior_date': fields.Date.today(),
            })
            rec.message_post(
                body=_('✅ كبير المهندسين — تقييم %s%s')
                % (rec.senior_grade.upper(),
                   ': ' + rec.senior_notes if rec.senior_notes else ''))

    # ── الوقف يعتمد نهائياً ──────────────────────────────
    def action_waqf_approve(self):
        for rec in self:
            rec.write({
                'state':     'approved',
                'waqf_by':   self.env.user.id,
                'waqf_date': fields.Date.today(),
            })
            rec.message_post(
                body=_('✅ الوقف اعتمد نهائياً — تقييم %s%s')
                % (rec.waqf_grade.upper(),
                   ': ' + rec.waqf_notes if rec.waqf_notes else ''))

    # ── رفض من أي مرحلة (زر عام) ────────────────────────
    def action_reject(self):
        for rec in self:
            if not (rec.reject_reason or '').strip():
                raise UserError(_('يرجى كتابة سبب الرفض.'))
            rec.write({'state': 'rejected'})
            rec.message_post(
                body=_('❌ مرفوض: %s') % rec.reject_reason)

    # ── إعادة فتح (للمسؤول) ──────────────────────────────
    def action_reset_draft(self):
        self.write({
            'state': 'draft',
            'engineer_grade': False, 'engineer_notes': False,
            'engineer_by': False, 'engineer_date': False,
            'senior_grade': False, 'senior_notes': False,
            'senior_by': False, 'senior_date': False,
            'waqf_grade': False, 'waqf_notes': False,
            'waqf_by': False, 'waqf_date': False,
            'reject_reason': False,
        })

    # ══════════════════════════════════════════════════════════
    #  تحقق الصلاحية لمسجد
    # ══════════════════════════════════════════════════════════
    def check_valid_for_mosque(self, mosque):
        self.ensure_one()
        if self.state != 'approved':
            return False
        if self.scope == 'all':
            return True
        return mosque in self.mosque_ids