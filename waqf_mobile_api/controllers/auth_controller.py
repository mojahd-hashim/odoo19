# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from .base import api_response, require_token, get_json_body
import secrets


class WaqfAuthController(http.Controller):

    # ── OPTIONS ───────────────────────────────────────────────────
    @http.route('/api/waqf/auth/<path:subpath>',
                type='http', auth='none', methods=['OPTIONS'], csrf=False)
    def options_auth(self, **kw):
        return api_response(data='ok')

    # ── POST /api/waqf/auth/login ─────────────────────────────────
    @http.route(['/api/waqf/auth/login', '/api/v1/waqf/auth/login'],
                type='http', auth='none', methods=['POST'], csrf=False)
    def login(self, **kwargs):
        body     = get_json_body()
        login    = body.get('login', '').strip()
        password = body.get('password', '')
        device   = body.get('device_info', '')

        if not login or not password:
            return api_response(error='login and password are required', status=400)

        # ── التحقق من بيانات الدخول ───────────────────────────────
        try:
            uid = request.env['res.users'].sudo()._login(
                {'type': 'password', 'login': login, 'password': password},
                {'interactive': False}
            )
        except Exception:
            uid = False

        if not uid:
            return api_response(error='Invalid credentials', status=401)

        # ── البحث في مستخدمي البوابة فقط ─────────────────────────
        portal_user = request.env['waqf.portal.user'].sudo().search(
            [('user_id.login', '=', login),
             ('is_active', '=', True)], limit=1)

        if not portal_user:
            return api_response(
                error='لا يوجد حساب بوابة مرتبط بهذا المستخدم. تواصل مع المسؤول.',
                status=403)

        if not portal_user.effective_mosque_ids:
            return api_response(
                error='لا توجد مساجد مخصصة لك. تواصل مع المسؤول.',
                status=403)

        # ── إنشاء التوكن ──────────────────────────────────────────
        token_raw = _generate_portal_token(
            portal_user, device,
            request.env['waqf.portal.token'].sudo()
        )
        # commit التوكن قبل أي عملية أخرى قد تفشل
        request.env.cr.commit()

        try:
            config = request.env['res.config.settings'].sudo().get_mobile_config()
        except Exception:
            config = {}

        return api_response(data={
            'token':       token_raw,
            'user':        _build_user_data(portal_user),
            'permissions': _build_permissions(portal_user),
            'mosques':     _build_mosques(portal_user),
            'config':      config,
        })

    # ── GET /api/waqf/auth/me ─────────────────────────────────────
    @http.route('/api/waqf/auth/me',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def me(self, employee=None, **kwargs):
        # استخرج portal_user من التوكن
        auth_header = request.httprequest.headers.get('Authorization', '')
        raw = auth_header[7:] if auth_header.startswith('Bearer ') else ''

        portal_user = _get_portal_user_from_token(raw, request.env)
        if not portal_user:
            return api_response(error='Unauthorized', status=401)

        return api_response(data={
            'employee':    _build_user_data(portal_user),
            'permissions': _build_permissions(portal_user),
            'mosques':     _build_mosques(portal_user),
        })

    # ── POST /api/waqf/auth/logout ────────────────────────────────
    @http.route('/api/waqf/auth/logout',
                type='http', auth='none', methods=['POST'], csrf=False)
    @require_token
    def logout(self, employee=None, **kwargs):
        auth_header = request.httprequest.headers.get('Authorization', '')
        raw = auth_header[7:] if auth_header.startswith('Bearer ') else ''
        token = _find_token(raw, request.env)
        if token:
            token.write({'is_active': False})
        return api_response(data={'logged_out': True})

        # ══════════════════════════════════════════════════════════════
        # دالة حذف الحساب (تعطيل) — أضفها في الـ controller
        # ══════════════════════════════════════════════════════════════

    @http.route('/api/account/deactivate', type='json', auth='user')
    def deactivate_account(self, **kw):
        """تعطيل حساب المستخدم الحالي (غير نشط) بدل الحذف الفعلي."""
        user = request.env.user

        # ① تسجيل الانصراف إن كان هناك حضور نشط
        try:
            attendance = request.env['hr.attendance'].sudo().search([
                ('employee_id.user_id', '=', user.id),
                ('check_out', '=', False),
            ], limit=1)
            if attendance:
                attendance.sudo().write({
                    'check_out': fields.Datetime.now(),
                })
        except Exception:
            pass

        # ② تعطيل سجل بوابة المقاول إن وُجد
        try:
            portal_user = request.env['waqf.portal.user'].sudo().search([
                ('user_id', '=', user.id),
            ])
            if portal_user:
                portal_user.action_toggle_active()
        except Exception:
            pass

        # # ③ تعطيل المستخدم نفسه (active = False)
        # #    نستخدم sudo لأن المستخدم لا يملك صلاحية تعطيل نفسه عادةً
        # user.sudo().write({'active': False})

        return {
            'success': True,
            'message': 'تم تعطيل الحساب بنجاح',
        }
    # ── POST /api/waqf/auth/fcm-token ─────────────────────────────
    @http.route('/api/waqf/auth/fcm-token',
                type='http', auth='none', methods=['POST'], csrf=False)
    @require_token
    def update_fcm_token(self, employee=None, **kwargs):
        body = get_json_body()
        fcm  = body.get('fcm_token', '').strip()
        if not fcm:
            return api_response(error='fcm_token is required', status=400)
        auth_header = request.httprequest.headers.get('Authorization', '')
        raw = auth_header[7:] if auth_header.startswith('Bearer ') else ''
        token = _find_token(raw, request.env)
        if token:
            token.write({'fcm_token': fcm})
        return api_response(data={'updated': True})


# ── Private Helpers ────────────────────────────────────────────────

def _generate_portal_token(portal_user, device, Token):
    """إنشاء أو تجديد توكن لمستخدم البوابة."""
    if device:
        old = Token.search([
            ('portal_user_id', '=', portal_user.id),
            ('device_info',    '=', device),
            ('is_active',      '=', True),
        ])
        old.write({'is_active': False})

    raw = 'waqf_' + secrets.token_hex(24)
    import hashlib
    token_hash = hashlib.sha256(raw.encode()).hexdigest()

    Token.create({
        'portal_user_id': portal_user.id,
        'token_hash':     token_hash,
        'device_info':    device or '',
        'is_active':      True,
    })
    return raw


def _find_token(raw, env):
    import hashlib
    if not raw:
        return None
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    return env['waqf.portal.token'].sudo().search(
        [('token_hash', '=', token_hash),
         ('is_active',  '=', True)], limit=1)


def _get_portal_user_from_token(raw, env):
    token = _find_token(raw, env)
    return token.portal_user_id if token else None


def _build_user_data(portal_user):
    role_labels = {
        'resident_engineer':   'مستشار مقيم',
        'site_supervisor':     'مشرف موقع',
        'contractor_admin':    'مشرف عام',
        'contractor_engineer': 'مهندس مقاول',
        'project_manager':     'مدير مشروع',
    }
    return {
        'id':           portal_user.id,
        'name':         portal_user.name,
        'email':        portal_user.email,
        'phone':        portal_user.phone or '',
        'job_title':    role_labels.get(portal_user.role, portal_user.role),
        'role':         portal_user.role,
        'user_type':    'portal',
        'company':      portal_user.company_id.name if portal_user.company_id else '',
        'avatar_url':   '/web/image/res.users/%d/avatar_128' % (
                         portal_user.user_id.id if portal_user.user_id else 0),
        'mosque_count': portal_user.mosque_count,
    }


def _build_permissions(portal_user):
    perm = portal_user.permission_id[:1]
    if not perm:
        return {}
    return {
        'can_submit_report':             perm.can_submit_report,
        'allowed_report_types':          perm.allowed_report_types.mapped('code'),
        'can_view_all_reports':          perm.can_view_all_reports,
        'can_approve_works':             perm.can_approve_works,
        'can_reject_works':              perm.can_reject_works,
        'can_view_boq_prices':           perm.can_view_boq_prices,
        'can_review_certificates':       perm.can_review_certificates,
        'can_approve_certificates':      perm.can_approve_certificates,
        'can_reject_certificates':       perm.can_reject_certificates,
        'can_submit_works':              perm.can_submit_works,
        'can_view_team_works':           perm.can_view_team_works,
        'can_submit_certificate':        perm.can_submit_certificate,
        'can_view_all_certificates':     perm.can_view_all_certificates,
        'can_request_change_order':      perm.can_request_change_order,
        'can_view_boq':                  perm.can_view_boq,
        'can_view_boq_prices_contractor':perm.can_view_boq_prices_contractor,
    }


def _build_mosques(portal_user):
    return [{
        'id':              m.id,
        'code':            m.code,
        'name':            m.name,
        'city':            m.city or '',
        'state':           m.state,
        'lat':             m.latitude,
        'lng':             m.longitude,
        'geofence_radius': m.geofence_radius or 100,
    } for m in portal_user.effective_mosque_ids]