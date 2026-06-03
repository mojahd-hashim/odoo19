# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import secrets, string


class WaqfPortalUser(models.Model):
    _name        = 'waqf.portal.user'
    _description = 'مستخدم بوابة كوقف'
    _inherit     = ['mail.thread', 'mail.activity.mixin']
    _order       = 'role, name'

    # ── Identity ───────────────────────────────────────────────
    name  = fields.Char(string='الاسم الكامل', required=True, tracking=True)
    email = fields.Char(string='البريد الإلكتروني', required=True, tracking=True)
    phone = fields.Char(string='رقم الجوال')

    user_id = fields.Many2one(
        'res.users', string='حساب أودو',
        ondelete='set null', tracking=True,
        help='يُنشأ تلقائياً عند الحفظ إذا لم يكن موجوداً')

    # ── Role ───────────────────────────────────────────────────
    role = fields.Selection([
        ('resident_engineer', 'مستشار مقيم'),
        ('site_supervisor',   'مشرف موقع (مقاول)'),
        ('contractor_admin',  'مشرف عام (مقاول)'),
        ('contractor_engineer','مهندس مقاول'),
        ('project_manager',   'مدير مشروع'),
    ], string='الدور', required=True, tracking=True)

    company_id = fields.Many2one(
        'res.partner', string='شركة المقاول',
        domain=[('is_company', '=', True)],
        help='للمقاولين فقط')

    # ── Access Scope ───────────────────────────────────────────
    access_mode = fields.Selection([
        ('all',      'كل المساجد'),
        ('phase',    'مرحلة محددة'),
        ('specific', 'مساجد محددة'),
    ], string='نطاق الوصول', default='phase', required=True)

    phase_ids = fields.Many2many(
        'mosque.package', string='المراحل المسموحة',
        help='يرى كل مساجد هذه المراحل')

    mosque_ids = fields.Many2many(
        'mosque.mosque', string='مساجد محددة',
        help='تتجاوز نطاق المرحلة — مساجد بعينها')

    # ── Status ─────────────────────────────────────────────────
    is_active    = fields.Boolean(string='نشط', default=True, tracking=True)
    invite_sent  = fields.Boolean(string='تم إرسال الدعوة', readonly=True)
    invite_date  = fields.Datetime(string='تاريخ الدعوة', readonly=True)
    last_login   = fields.Datetime(
        string='آخر دخول', related='user_id.login_date', readonly=True)

    # ── Computed: effective mosques ────────────────────────────
    effective_mosque_ids = fields.Many2many(
        'mosque.mosque', string='المساجد الفعلية',
        compute='_compute_effective_mosques',
        help='المساجد التي يراها المستخدم فعلياً')

    mosque_count = fields.Integer(
        compute='_compute_effective_mosques', string='عدد المساجد')

    # ── Permissions (One2one via related) ─────────────────────
    permission_id = fields.One2many(
        'waqf.portal.permission', 'portal_user_id',
        string='الصلاحيات', limit=1)

    # ── Portal URL ─────────────────────────────────────────────
    portal_url = fields.Char(
        string='رابط البوابة', compute='_compute_portal_url')

    # ── Computed ───────────────────────────────────────────────
    @api.depends('access_mode', 'phase_ids', 'mosque_ids')
    def _compute_effective_mosques(self):
        Mosque = self.env['mosque.mosque'].sudo()
        for rec in self:
            if rec.access_mode == 'all':
                mosques = Mosque.search([('active', '=', True)])
            elif rec.access_mode == 'phase' and rec.phase_ids:
                mosques = Mosque.search([
                    ('package_id', 'in', rec.phase_ids.ids),
                    ('active', '=', True),
                ])
            elif rec.access_mode == 'specific' and rec.mosque_ids:
                mosques = rec.mosque_ids
            else:
                mosques = Mosque.browse()
            rec.effective_mosque_ids = mosques
            rec.mosque_count = len(mosques)

    @api.depends('role')
    def _compute_portal_url(self):
        base = self.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', 'https://masajed.kawaqf.org')
        for rec in self:
            path = '/contractor' if rec.role in (
                'site_supervisor', 'contractor_admin',
                'contractor_engineer') else '/portal'
            rec.portal_url = base + path

    # ── Constraints ────────────────────────────────────────────
    @api.constrains('email')
    def _check_email(self):
        for rec in self:
            if rec.email and '@' not in rec.email:
                raise ValidationError('البريد الإلكتروني غير صحيح')

    @api.constrains('role', 'company_id')
    def _check_company(self):
        contractor_roles = ('site_supervisor', 'contractor_admin',
                            'contractor_engineer')
        for rec in self:
            if rec.role in contractor_roles and not rec.company_id:
                raise ValidationError(
                    'يجب تحديد شركة المقاول لهذا الدور')

    # ── Create / Write ─────────────────────────────────────────
    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            rec._ensure_odoo_user()
            rec._ensure_permission()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'is_active' in vals:
            for rec in self:
                if rec.user_id:
                    rec.user_id.sudo().write({'active': vals['is_active']})
        return res

    def _ensure_odoo_user(self):
        """Create or link Odoo portal user."""
        if self.user_id:
            return
        existing = self.env['res.users'].sudo().search(
            [('login', '=', self.email)], limit=1)
        if existing:
            self.user_id = existing
            return
        # Create portal user
        password = self._generate_password()
        user = self.env['res.users'].sudo().create({
            'name':     self.name,
            'login':    self.email,
            'email':    self.email,
            'password': password,
            'active':   self.is_active,
        })
        # ② إضافته لمجموعة البوابة
        portal_group = self.env.ref('base.group_portal')
        portal_group.sudo().write({
            'user_ids': [(4, user.id)]
        })
        self.sudo().write({
            'user_id':    user.id,
            '_temp_pass': password,
        })

    def _ensure_permission(self):
        """Create default permission record."""
        if not self.permission_id:
            self.env['waqf.portal.permission'].create({
                'portal_user_id': self.id,
            })

    @staticmethod
    def _generate_password(length=12):
        chars = string.ascii_letters + string.digits + '!@#$'
        return ''.join(secrets.choice(chars) for _ in range(length))

    # ── Temp password (not stored in DB — used once) ──────────
    _temp_pass = fields.Char(store=False)

    # ── Actions ────────────────────────────────────────────────
    def action_send_invite(self):
        """Send invitation email with portal link and credentials."""
        self.ensure_one()
        template = self.env.ref(
            'waqf_portal_access.mail_template_portal_invite',
            raise_if_not_found=False)
        if template:
            template.send_mail(self.id, force_send=True)
        self.write({
            'invite_sent': True,
            'invite_date': fields.Datetime.now(),
        })
        return {
            'type':    'ir.actions.client',
            'tag':     'display_notification',
            'params': {
                'title':   'تم إرسال الدعوة',
                'message': f'تم إرسال دعوة الدخول إلى {self.email}',
                'type':    'success',
                'sticky':  False,
            }
        }

    def action_toggle_active(self):
        for rec in self:
            rec.write({'is_active': not rec.is_active})

    def action_reset_password(self):
        """Send password reset email."""
        self.ensure_one()
        if self.user_id:
            self.user_id.sudo().action_reset_password()
        return {
            'type':    'ir.actions.client',
            'tag':     'display_notification',
            'params': {
                'title':   'تم الإرسال',
                'message': 'تم إرسال رابط إعادة تعيين كلمة المرور',
                'type':    'success',
            }
        }

    def action_view_mosques(self):
        self.ensure_one()
        return {
            'type':      'ir.actions.act_window',
            'name':      f'مساجد {self.name}',
            'res_model': 'mosque.mosque',
            'view_mode': 'list,form',
            'domain':    [('id', 'in', self.effective_mosque_ids.ids)],
        }
