from odoo import http
from odoo.http import request
from .base import api_response, require_token, get_json_body
import json


class WaqfAuthController(http.Controller):

    # ── OPTIONS (CORS preflight) ──────────────────────────────────
    @http.route('/api/waqf/auth/<path:subpath>',
                type='http', auth='none', methods=['OPTIONS'], csrf=False)
    def options_auth(self, **kw):
        return api_response(data='ok')

    # ── POST /api/waqf/auth/login ─────────────────────────────────
    @http.route('/api/waqf/auth/login','/api/v1/waqf/auth/login',
                type='http', auth='none', methods=['POST'], csrf=False)
    def login(self, **kwargs):
        """
        Authenticate with Odoo credentials + return API token.

        Request body:
        {
            "login": "employee@kawaqf.org",
            "password": "...",
            "device_info": "iPhone 14 / iOS 17.2"  (optional)
        }

        Response:
        {
            "token": "waqf_...",
            "employee": { id, name, job_title, mosque_count },
            "config": { geofence, report, notifications, app }
        }
        """
        body = get_json_body()
        login    = body.get('login', '').strip()
        password = body.get('password', '')
        device   = body.get('device_info', '')

        if not login or not password:
            return api_response(error='login and password are required', status=400)

        # Authenticate against Odoo
        db  = request.env.cr.dbname
        uid = request.session.authenticate(db, login, password)
        if not uid:
            return api_response(error='Invalid credentials', status=401)

        # Find employee record
        employee = request.env['hr.employee'].sudo().search(
            [('user_id.login', '=', login)], limit=1)
        if not employee:
            return api_response(
                error='No employee record linked to this user. '
                      'Contact your administrator.', status=403)

        # Check has assigned mosques
        if not employee.all_mosque_ids:
            return api_response(
                error='No mosques assigned to you. '
                      'Contact your administrator.', status=403)

        # Revoke old tokens for this device if same device_info
        if device:
            old = request.env['waqf.api.token'].sudo().search([
                ('employee_id', '=', employee.id),
                ('device_info', '=', device),
                ('is_active',   '=', True),
            ])
            old.write({'is_active': False})

        # Generate new token
        raw, token_id = request.env['waqf.api.token'].sudo().generate_token(
            employee.id, name='Mobile Login')

        if device:
            request.env['waqf.api.token'].sudo().browse(token_id).write(
                {'device_info': device})

        # Get app config
        config = request.env['res.config.settings'].sudo().get_mobile_config()

        return api_response(data={
            'token':    raw,
            'employee': _employee_data(employee),
            'config':   config,
        })

    # ── GET /api/waqf/auth/me ─────────────────────────────────────
    @http.route('/api/waqf/auth/me',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def me(self, employee=None, **kwargs):
        """Return current user profile + assigned mosques summary."""
        mosques = employee.all_mosque_ids
        return api_response(data={
            'employee': _employee_data(employee),
            'mosques': [{
                'id':    m.id,
                'code':  m.code,
                'name':  m.name,
                'city':  m.city,
                'state': m.state,
                'lat':   m.latitude,
                'lng':   m.longitude,
                'geofence_radius': m.geofence_radius or 100,
            } for m in mosques],
        })

    # ── POST /api/waqf/auth/fcm-token ─────────────────────────────
    @http.route('/api/waqf/auth/fcm-token',
                type='http', auth='none', methods=['POST'], csrf=False)
    @require_token
    def update_fcm_token(self, employee=None, **kwargs):
        """Update Firebase push notification token."""
        body = get_json_body()
        fcm = body.get('fcm_token', '').strip()
        if not fcm:
            return api_response(error='fcm_token is required', status=400)

        employee.sudo().write({'fcm_token': fcm})

        # Also update on the API token
        auth_header = request.httprequest.headers.get('Authorization', '')
        raw = auth_header[7:]
        token_hash = request.env['waqf.api.token']._hash_token(raw)
        token = request.env['waqf.api.token'].sudo().search(
            [('token_hash', '=', token_hash)], limit=1)
        if token:
            token.write({'fcm_token': fcm})

        return api_response(data={'updated': True})

    # ── POST /api/waqf/auth/logout ────────────────────────────────
    @http.route('/api/waqf/auth/logout',
                type='http', auth='none', methods=['POST'], csrf=False)
    @require_token
    def logout(self, employee=None, **kwargs):
        """Revoke current token."""
        auth_header = request.httprequest.headers.get('Authorization', '')
        raw = auth_header[7:]
        token_hash = request.env['waqf.api.token']._hash_token(raw)
        token = request.env['waqf.api.token'].sudo().search(
            [('token_hash', '=', token_hash)], limit=1)
        if token:
            token.write({'is_active': False})
        return api_response(data={'logged_out': True})


def _employee_data(employee):
    return {
        'id':            employee.id,
        'name':          employee.name,
        'job_title':     employee.job_title or '',
        'email':         employee.work_email or '',
        'phone':         employee.mobile_phone or '',
        'mosque_count':  len(employee.all_mosque_ids),
        'avatar_url':    '/web/image/hr.employee/%d/avatar_128' % employee.id,
    }
