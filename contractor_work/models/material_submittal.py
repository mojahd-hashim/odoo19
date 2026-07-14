# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError


class ContractorMaterialSubmittal(models.Model):
    """عينات المواد — مطلوبة لبعض بنود BOQ."""
    _name        = 'contractor.material.submittal'
    _description = 'عينة مادة'
    _inherit     = ['mail.thread']
    _order       = 'date_submitted desc'

    name = fields.Char(
        string='رقم العينة', readonly=True,
        copy=False, default='جديد')

    work_order_id = fields.Many2one(
        'contractor.work.order', string='أمر العمل',
        ondelete='cascade')

    mosque_id = fields.Many2one(
        'mosque.mosque', string='المسجد')
    mosque_ids = fields.Many2many(
        'mosque.mosque', string='المسجد')

    boq_id = fields.Many2one(
        'mosque.boq', string='البند المرتبط',
        required=True)

    material_name   = fields.Char(string='اسم المادة', required=True)
    manufacturer    = fields.Char(string='المصنع / المورد')
    model_number    = fields.Char(string='رقم الموديل')
    specifications  = fields.Text(string='المواصفات الفنية')

    date_submitted  = fields.Date(string='تاريخ التقديم', default=fields.Date.today)

    document_ids = fields.Many2many(
        'ir.attachment',
        'submittal_docs_rel', 'sub_id', 'att_id',
        string='الوثائق والصور')

    state = fields.Selection([
        ('draft', 'مسودة'),
        ('submitted', 'بانتظار المراجعة'),
        ('submitted_waqf', 'بانتظار اعتماد الوقف'),
        ('approved', 'معتمد — A'),
        ('approved_b', 'معتمد مع ملاحظات — B'),
        ('revision', 'يلزم تعديل — C (إعادة إرسال)'),
        ('rejected', 'مرفوض — D'),
    ], string='الحالة', default='draft', tracking=True, index=True)

    approved_by    = fields.Many2one('res.users', string='اعتمد بواسطة', readonly=True)
    approval_date  = fields.Date(string='تاريخ الاعتماد', readonly=True)
    reject_reason  = fields.Text(string='سبب الرفض')
    notes          = fields.Text(string='ملاحظات المستشار')
    GRADE_SELECTION = [
        ('a', 'A — معتمد بالكامل'),
        ('b', 'B — معتمد مع ملاحظات'),
        ('c', 'C — يلزم تعديل وإعادة إرسال'),
        ('d', 'D — مرفوض'),
    ]

    grade = fields.Selection(
        GRADE_SELECTION, string='التقييم', tracking=True)
    review_notes = fields.Text(
        string='ملاحظات الاستشاري', tracking=True)
    reviewed_by = fields.Many2one(
        'res.users', string='راجع بواسطة', readonly=True)
    review_date = fields.Datetime(
        string='تاريخ المراجعة', readonly=True)

    # ══════════════════════════════════════════════════════════
    #  المراجعات (Revisions)
    # ══════════════════════════════════════════════════════════
    revision = fields.Integer(
        string='رقم الإصدار', default=0, tracking=True)

    display_name_rev = fields.Char(
        string='الرقم + الإصدار',
        compute='_compute_display_name_rev', store=True)

    revision_log_ids = fields.One2many(
        'contractor.submittal.revision', 'submittal_id',
        string='سجل المراجعات')

    @api.depends('name', 'revision')
    def _compute_display_name_rev(self):
        for rec in self:
            if rec.revision > 0:
                rec.display_name_rev = '%s (Rev.%d)' % (
                    rec.name or '', rec.revision)
            else:
                rec.display_name_rev = rec.name or ''

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'جديد') == 'جديد':
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'contractor.material.submittal') or 'جديد'
        return super().create(vals_list)

        # ══════════════════════════════════════════════════════════
        #  Actions
        # ══════════════════════════════════════════════════════════

    def action_submit(self):
        """المقاول يرسل العينة."""
        for rec in self:
            rec.write({'state': 'submitted'})
            rec.message_post(
                body=_('📋 تم إرسال العينة للمراجعة (إصدار %d)') % rec.revision)

    def action_grade(self):
        """الاستشاري يقيّم العينة بـ A/B/C/D."""
        for rec in self:
            if not rec.grade:
                raise UserError(_('يرجى اختيار التقييم (A/B/C/D).'))
            if rec.grade in ('b', 'c', 'd') and not (rec.review_notes or '').strip():
                raise UserError(
                    _('التقييم %s يتطلب كتابة الملاحظات.')
                    % rec.grade.upper())

            state_map = {
                'a': 'approved',
                'b': 'approved_b',
                'c': 'revision',
                'd': 'rejected',
            }
            if rec.state in ['submitted']:
                rec.write({
                    'state': state_map[rec.grade],
                    'reviewed_by': self.env.user.id,
                    'review_date': fields.Datetime.now(),
                })
                # سجّل في log المراجعات
                self.env['contractor.submittal.revision'].create({
                    'submittal_id': rec.id,
                    'revision': rec.revision,
                    'grade': rec.grade,
                    'notes': rec.review_notes,
                    'reviewed_by': self.env.user.id,
                    'date': fields.Datetime.now(),
                })

                grade_labels = {
                    'a': 'A — معتمد',
                    'b': 'B — معتمد مع ملاحظات',
                    'c': 'C — يلزم تعديل',
                    'd': 'D — مرفوض',
                }
                rec.message_post(
                    body=_('📝 التقييم: %s%s') % (
                        grade_labels[rec.grade],
                        '\n' + rec.review_notes if rec.review_notes else ''))
            else:
                rec.write({
                    'state': 'submitted_waqf',
                })
                grade_labels = {
                    'a': 'A — معتمد',
                    'b': 'B — معتمد مع ملاحظات',
                    'c': 'C — يلزم تعديل',
                    'd': 'D — مرفوض',
                }
                rec.message_post(
                    body=_('📝 اعتمد الوقف التقييم: %s%s') % (
                        grade_labels[rec.grade],
                        '\n' + rec.review_notes if rec.review_notes else ''))



    def action_resubmit(self):
        """المقاول يعيد الإرسال بعد التعديل (فقط عند C)."""
        for rec in self:
            if rec.state != 'revision':
                raise UserError(
                    _('لا يمكن إعادة الإرسال إلا عند حالة "يلزم تعديل — C".'))
            rec.write({
                'state': 'submitted',
                'revision': rec.revision + 1,
                'grade': False,
                'review_notes': False,
                'reviewed_by': False,
                'review_date': False,
            })
            rec.message_post(
                body=_('🔄 تم إعادة الإرسال — إصدار %d') % rec.revision)

    class ContractorSubmittalRevision(models.Model):
        """سجل مراجعات العينة — كل تقييم يُحفظ هنا."""
        _name = 'contractor.submittal.revision'
        _description = 'سجل مراجعة العينة'
        _order = 'date desc'

        submittal_id = fields.Many2one(
            'contractor.material.submittal', string='العينة',
            required=True, ondelete='cascade', index=True)
        revision = fields.Integer(string='رقم الإصدار')
        grade = fields.Selection([
            ('a', 'A'), ('b', 'B'), ('c', 'C'), ('d', 'D'),
        ], string='التقييم')
        notes = fields.Text(string='ملاحظات الاستشاري')
        reviewed_by = fields.Many2one(
            'res.users', string='المراجع')
        date = fields.Datetime(string='التاريخ')

        # ── ملخص التعديلات التي أجراها المقاول ──
        contractor_changes = fields.Text(
            string='ملخص التعديلات')

