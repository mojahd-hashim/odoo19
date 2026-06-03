# -*- coding: utf-8 -*-
from odoo import http
from odoo.http import request
from .base import api_response, require_token, haversine_distance, get_json_body
from datetime import datetime, timedelta


class WaqfAttendanceController(http.Controller):

    # ── POST /api/waqf/attendance/checkin ─────────────────────────
    @http.route('/api/waqf/attendance/checkin',
                type='http', auth='none', methods=['POST'], csrf=False)
    @require_token
    def checkin(self, employee=None, **kwargs):
        portal_user = kwargs.get('portal_user')
        body        = get_json_body()
        mosque_id   = body.get('mosque_id')
        lat         = body.get('lat')
        lng         = body.get('lng')
        qr_token    = body.get('qr_token', '')
        idem_key    = body.get('idempotency_key', '')

        if not all([mosque_id, lat, lng]):
            return api_response(error='mosque_id, lat, lng are required', status=400)

        user_type, user_id, allowed_mosques = _resolve_user(employee, portal_user)
        if not user_id:
            return api_response(error='Unauthorized', status=401)

        # Idempotency check
        if idem_key:
            existing = request.env['mosque.attendance'].sudo().search(
                [('mobile_token', '=', idem_key)], limit=1)
            if existing:
                return api_response(data={
                    'attendance_id':   existing.id,
                    'is_validated':    existing.is_validated,
                    'distance_m':      existing.distance_m,
                    'within_geofence': existing.distance_m <= (
                        existing.mosque_id.geofence_radius or 100),
                    'check_in':        str(existing.check_in),
                    'duplicate':       True,
                })

        mosque = request.env['mosque.mosque'].sudo().browse(int(mosque_id))
        if not mosque.exists():
            return api_response(error='Mosque not found', status=404)

        # Verify access
        if mosque not in allowed_mosques:
            return api_response(error='Not assigned to this mosque', status=403)

        # Already checked in?
        domain_active = [('mosque_id', '=', mosque.id), ('check_out', '=', False)]
        if user_type == 'employee':
            domain_active.append(('engineer_id', '=', user_id))
        else:
            domain_active.append(('portal_user_id', '=', portal_user.user_id.id))

        active = request.env['mosque.attendance'].sudo().search(domain_active, limit=1)
        if active:
            return api_response(
                error='Already checked in. Please checkout first.', status=409)

        # Distance
        distance = 0.0
        if mosque.latitude and mosque.longitude:
            distance = haversine_distance(lat, lng, mosque.latitude, mosque.longitude)

        radius       = mosque.geofence_radius or 100
        within_fence = distance <= radius
        qr_ok        = bool(qr_token and mosque.qr_code == qr_token)

        now  = datetime.now()
        vals = {
            'mosque_id':     mosque.id,
            'visit_type':    'field',
            'check_in':      now,
            'gps_latitude':  lat,
            'gps_longitude': lng,
            'gps_validated': within_fence,
            'qr_validated':  qr_ok,
            'distance_m':    round(distance, 1),
            'mobile_token':  idem_key or False,
        }
        if user_type == 'employee':
            vals['engineer_id'] = user_id
        else:
            vals['portal_user_id'] = portal_user.user_id.id

        attendance = request.env['mosque.attendance'].sudo().create(vals)

        return api_response(data={
            'attendance_id':   attendance.id,
            'is_validated':    attendance.is_validated,
            'distance_m':      round(distance, 1),
            'within_geofence': within_fence,
            'qr_validated':    qr_ok,
            'check_in':        str(now),
            'geofence_radius': radius,
            'warning':         None if within_fence else
                               'أنت خارج النطاق الجغرافي للمسجد (%.0f م).' % distance,
        })

    # ── POST /api/waqf/attendance/checkout ───────────────────────
    @http.route('/api/waqf/attendance/checkout',
                type='http', auth='none', methods=['POST'], csrf=False)
    @require_token
    def checkout(self, employee=None, **kwargs):
        portal_user    = kwargs.get('portal_user')
        body           = get_json_body()
        attendance_id  = body.get('attendance_id')
        auto_triggered = body.get('auto_triggered', False)

        if not attendance_id:
            return api_response(error='attendance_id is required', status=400)

        user_type, user_id, _ = _resolve_user(employee, portal_user)
        if not user_id:
            return api_response(error='Unauthorized', status=401)

        attendance = request.env['mosque.attendance'].sudo().browse(int(attendance_id))
        if not attendance.exists():
            return api_response(error='Attendance record not found', status=404)

        # تحقق من الملكية
        if user_type == 'employee':
            if attendance.engineer_id.id != user_id:
                return api_response(error='Not your attendance record', status=403)
        else:
            if attendance.portal_user_id.id != user_id:
                return api_response(error='Not your attendance record', status=403)

        if attendance.check_out:
            return api_response(error='Already checked out', status=409)

        now      = datetime.now()
        duration = (now - attendance.check_in).total_seconds() / 3600
        attendance.write({'check_out': now})

        ICP         = request.env['ir.config_parameter'].sudo()
        min_minutes = int(ICP.get_param('waqf.mobile.min_visit_minutes', 30))
        is_short    = duration * 60 < min_minutes

        return api_response(data={
            'attendance_id':  attendance.id,
            'check_in':       str(attendance.check_in),
            'check_out':      str(now),
            'duration_hrs':   round(duration, 2),
            'duration_label': _format_duration(duration),
            'is_validated':   attendance.is_validated,
            'auto_triggered': auto_triggered,
            'short_visit':    is_short,
            'short_warning':  ('زيارة قصيرة — أقل من %d دقيقة' % min_minutes)
                              if is_short else None,
        })

    # ── GET /api/waqf/attendance/active ──────────────────────────
    @http.route('/api/waqf/attendance/active',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def active_checkin(self, employee=None, **kwargs):
        portal_user = kwargs.get('portal_user')
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info('ACTIVE_DEBUG employee=%s portal_user=%s', employee, portal_user)
        user_type, user_id, _ = _resolve_user(employee, portal_user)
        _logger.info('ACTIVE_DEBUG user_type=%s user_id=%s', user_type, user_id)
        portal_user = kwargs.get('portal_user')
        user_type, user_id, _ = _resolve_user(employee, portal_user)

        if not user_id:
            return api_response(data={'active': False})

        if user_type == 'employee':
            domain = [('engineer_id', '=', user_id), ('check_out', '=', False)]
        else:
            domain = [('portal_user_id', '=', user_id), ('check_out', '=', False)]

        active = request.env['mosque.attendance'].sudo().search(
            domain, order='check_in desc', limit=1)

        if not active:
            return api_response(data={'active': False})

        elapsed   = (datetime.now() - active.check_in).total_seconds() / 3600
        ICP       = request.env['ir.config_parameter'].sudo()
        max_hours = int(ICP.get_param('waqf.mobile.long_stay_hours', 8))

        return api_response(data={
            'active':          True,
            'attendance_id':   active.id,
            'mosque_id':       active.mosque_id.id,
            'mosque_name':     active.mosque_id.name,
            'mosque_code':     active.mosque_id.code,
            'mosque_lat':      active.mosque_id.latitude,
            'mosque_lng':      active.mosque_id.longitude,
            'mosque_radius':   active.mosque_id.geofence_radius or 100,
            'check_in':        str(active.check_in),
            'elapsed_hrs':     round(elapsed, 2),
            'elapsed_label':   _format_duration(elapsed),
            'long_stay_alert': elapsed > max_hours,
        })

    # ── GET /api/waqf/attendance/history ─────────────────────────
    @http.route('/api/waqf/attendance/history',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def history(self, employee=None, **kwargs):
        portal_user = kwargs.get('portal_user')
        user_type, user_id, _ = _resolve_user(employee, portal_user)

        if not user_id:
            return api_response(error='Unauthorized', status=401)

        mosque_id = request.httprequest.args.get('mosque_id')
        days      = int(request.httprequest.args.get('days', 30))
        since     = datetime.now() - timedelta(days=days)

        if user_type == 'employee':
            domain = [('engineer_id', '=', user_id), ('check_in', '>=', since)]
        else:
            domain = [('portal_user_id', '=', user_id), ('check_in', '>=', since)]

        if mosque_id:
            domain.append(('mosque_id', '=', int(mosque_id)))

        visits = request.env['mosque.attendance'].sudo().search(
            domain, order='check_in desc', limit=100)

        return api_response(data={
            'visits': [{
                'id':             v.id,
                'mosque_id':      v.mosque_id.id,
                'mosque_name':    v.mosque_id.name,
                'mosque_code':    v.mosque_id.code,
                'check_in':       str(v.check_in),
                'check_out':      str(v.check_out) if v.check_out else None,
                'duration':       v.duration,
                'duration_label': _format_duration(v.duration),
                'is_validated':   v.is_validated,
                'distance_m':     v.distance_m,
            } for v in visits],
            'total': len(visits),
            'days':  days,
        })


# ── Helpers ────────────────────────────────────────────────────────

def _resolve_user(employee, portal_user):
    if employee:
        return ('employee', employee.id, employee.all_mosque_ids)
    if portal_user:
        # استخدم res.users.id وليس waqf.portal.user.id
        return ('portal', portal_user.user_id.id, portal_user.effective_mosque_ids)
    return (None, None, [])


def _format_duration(hours):
    if not hours:
        return '0 دقيقة'
    h = int(hours)
    m = int((hours - h) * 60)
    if h == 0:   return '%d دقيقة' % m
    if m == 0:   return '%d ساعة' % h
    return '%d ساعة %d دقيقة' % (h, m)