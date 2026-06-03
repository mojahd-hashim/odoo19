# -*- coding: utf-8 -*-
from odoo import models, fields, api


class WaqfPortalPermission(models.Model):
    _name        = 'waqf.portal.permission'
    _description = 'صلاحيات مستخدم البوابة'
    _rec_name = 'role'

    portal_user_id = fields.Many2one(
        'waqf.portal.user', required=True, ondelete='cascade')

    role = fields.Selection(
        related='portal_user_id.role', readonly=True, store=True)

    # ═══════════════════════════════════════════════════════
    # CONSULTANT PERMISSIONS
    # ═══════════════════════════════════════════════════════

    # التقارير
    can_submit_report = fields.Boolean(
        string='رفع تقارير الزيارة', default=True)
    allowed_report_types = fields.Many2many(
        'waqf.report.type', string='أنواع التقارير المسموحة')
    can_view_all_reports = fields.Boolean(
        string='مشاهدة تقارير الآخرين', default=False)

    # الأعمال
    can_approve_works = fields.Boolean(
        string='اعتماد أعمال المقاول', default=True)
    can_reject_works = fields.Boolean(
        string='رفض أعمال المقاول', default=True)
    can_view_boq_prices = fields.Boolean(
        string='مشاهدة أسعار جدول الكميات', default=True)

    # المستخلصات
    can_review_certificates = fields.Boolean(
        string='مراجعة المستخلصات', default=True)
    can_approve_certificates = fields.Boolean(
        string='اعتماد المستخلصات', default=False)
    can_reject_certificates = fields.Boolean(
        string='رفض المستخلصات', default=False)

    # ═══════════════════════════════════════════════════════
    # CONTRACTOR PERMISSIONS
    # ═══════════════════════════════════════════════════════

    # الأعمال
    can_submit_works = fields.Boolean(
        string='تسجيل أعمال منجزة', default=True)
    can_view_team_works = fields.Boolean(
        string='مشاهدة أعمال الفريق', default=False,
        help='للمشرفين فقط')

    # المستخلصات
    can_submit_certificate = fields.Boolean(
        string='إنشاء مستخلص', default=False)
    can_view_all_certificates = fields.Boolean(
        string='مشاهدة كل المستخلصات', default=False)

    # أوامر التغيير
    can_request_change_order = fields.Boolean(
        string='طلب أمر تغيير', default=False)

    # BOQ
    can_view_boq = fields.Boolean(
        string='مشاهدة جدول الكميات', default=True)
    can_view_boq_prices_contractor = fields.Boolean(
        string='مشاهدة الأسعار في جدول الكميات', default=False)

    # ═══════════════════════════════════════════════════════
    # AUTO-DEFAULTS BY ROLE
    # ═══════════════════════════════════════════════════════
    @api.onchange('role')
    def _onchange_role(self):
        defaults = self._get_role_defaults(self.role)
        for field, value in defaults.items():
            setattr(self, field, value)

    @api.model
    def _get_role_defaults(self, role):
        """Default permissions per role."""
        if role == 'resident_engineer':
            return {
                'can_submit_report':       True,
                'can_view_all_reports':    False,
                'can_approve_works':       True,
                'can_reject_works':        True,
                'can_view_boq_prices':     True,
                'can_review_certificates': True,
                'can_approve_certificates':False,
                'can_submit_works':        False,
                'can_submit_certificate':  False,
                'can_request_change_order':False,
            }
        elif role == 'contractor_admin':
            return {
                'can_submit_report':           False,
                'can_approve_works':           False,
                'can_view_boq_prices':         True,
                'can_submit_works':            True,
                'can_view_team_works':         True,
                'can_submit_certificate':      True,
                'can_view_all_certificates':   True,
                'can_request_change_order':    True,
                'can_view_boq_prices_contractor': True,
            }
        elif role == 'site_supervisor':
            return {
                'can_submit_report':           False,
                'can_approve_works':           False,
                'can_submit_works':            True,
                'can_view_team_works':         True,
                'can_submit_certificate':      True,
                'can_view_all_certificates':   False,
                'can_request_change_order':    True,
                'can_view_boq_prices_contractor': False,
            }
        elif role == 'contractor_engineer':
            return {
                'can_submit_report':           False,
                'can_approve_works':           False,
                'can_submit_works':            True,
                'can_view_team_works':         False,
                'can_submit_certificate':      False,
                'can_request_change_order':    False,
                'can_view_boq_prices_contractor': False,
            }
        elif role == 'project_manager':
            return {
                'can_submit_report':       True,
                'can_view_all_reports':    True,
                'can_approve_works':       True,
                'can_reject_works':        True,
                'can_view_boq_prices':     True,
                'can_review_certificates': True,
                'can_approve_certificates':True,
                'can_view_team_works':     True,
                'can_view_all_certificates':True,
            }
        return {}


class WaqfReportType(models.Model):
    """أنواع التقارير المتاحة للتحديد في الصلاحيات."""
    _name        = 'waqf.report.type'
    _description = 'نوع تقرير الزيارة'

    name = fields.Char(required=True)
    code = fields.Char(required=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'كود التقرير يجب أن يكون فريداً'),
    ]
