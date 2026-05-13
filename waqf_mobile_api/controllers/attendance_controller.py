from odoo import http
from odoo.http import request
from .base import api_response, require_token, haversine_distance, get_json_body
from datetime import datetime, date


class WaqfAttendanceController(http.Controller):

    # ── POST /api/waqf/attendance/checkin ─────────────────────────
    @http.route('/api/waqf/attendance/checkin',
                type='http', auth='none', methods=['POST'], csrf=False)
    @require_token
    def checkin(self, employee=None, **kwargs):
        """
        Register check-in with GPS validation.

        Request:
        {
            "mosque_id": 12,
            "lat": 24.7136,
            "lng": 46.6753,
            "qr_token": "QR100016",       (optional)
            "idempotency_key": "uuid"      (optional — prevent duplicates)
        }

        Response:
        {
            "attendance_id": 45,
            "is_validated": true,
            "distance_m": 42.3,
            "within_geofence": true,
            "check_in": "2026-05-12T09:15:33"
        }
        """
        body      = get_json_body()
        mosque_id = body.get('mosque_id')
        lat       = body.get('lat')
        lng       = body.get('lng')
        qr_token  = body.get('qr_token', '')
        idem_key  = body.get('idempotency_key', '')

        if not all([mosque_id, lat, lng]):
            return api_response(
                error='mosque_id, lat, lng are required', status=400)

        # Idempotency check — prevent duplicate check-ins
        if idem_key:
            existing = request.env['mosque.attendance'].sudo().search([
                ('mobile_token', '=', idem_key)], limit=1)
            if existing:
                return api_response(data={
                    'attendance_id': existing.id,
                    'is_validated':  existing.is_validated,
                    'distance_m':    existing.distance_m,
                    'within_geofence': existing.distance_m <= (
                        existing.mosque_id.geofence_radius or 100),
                    'check_in':      str(existing.check_in),
                    'duplicate':     True,
                })

        mosque = request.env['mosque.mosque'].sudo().browse(int(mosque_id))
        if not mosque.exists():
            return api_response(error='Mosque not found', status=404)

        # Verify access
        if mosque not in employee.all_mosque_ids:
            return api_response(error='Not assigned to this mosque', status=403)

        # Check already checked in
        active = request.env['mosque.attendance'].sudo().search([
            ('engineer_id', '=', employee.id),
            ('mosque_id',   '=', mosque.id),
            ('check_out',   '=', False),
        ], limit=1)
        if active:
            return api_response(error='Already checked in at this mosque. '
                                      'Please checkout first.', status=409)

        # Calculate distance
        distance = 0.0
        if mosque.latitude and mosque.longitude:
            distance = haversine_distance(
                lat, lng, mosque.latitude, mosque.longitude)

        radius       = mosque.geofence_radius or 100
        within_fence = distance <= radius
        qr_ok        = bool(qr_token and mosque.qr_code == qr_token)

        # Create attendance record
        now = datetime.now()
        attendance = request.env['mosque.attendance'].sudo().create({
            'mosque_id':    mosque.id,
            'engineer_id':  employee.id,
            'visit_type':   'field',
            'check_in':     now,
            'gps_latitude': lat,
            'gps_longitude': lng,
            'gps_validated': within_fence,
            'qr_validated':  qr_ok,
            'distance_m':    round(distance, 1),
            'mobile_token':  idem_key or False,
        })

        return api_response(data={
            'attendance_id':   attendance.id,
            'is_validated':    attendance.is_validated,
            'distance_m':      round(distance, 1),
            'within_geofence': within_fence,
            'qr_validated':    qr_ok,
            'check_in':        str(now),
            'geofence_radius': radius,
            'warning':         None if within_fence else
                               'أنت خارج النطاق الجغرافي للمسجد (%.0f م). '
                               'الزيارة مسجلة لكن غير موثقة.' % distance,
        })

    # ── POST /api/waqf/attendance/checkout ───────────────────────
    @http.route('/api/waqf/attendance/checkout',
                type='http', auth='none', methods=['POST'], csrf=False)
    @require_token
    def checkout(self, employee=None, **kwargs):
        """
        Register checkout — manual or triggered by geofence exit.

        Request:
        {
            "attendance_id": 45,   (required)
            "lat": 24.712,
            "lng": 46.678,
            "auto_triggered": true  (true = geofence exit, false = manual)
        }
        """
        body           = get_json_body()
        attendance_id  = body.get('attendance_id')
        lat            = body.get('lat')
        lng            = body.get('lng')
        auto_triggered = body.get('auto_triggered', False)

        if not attendance_id:
            return api_response(error='attendance_id is required', status=400)

        attendance = request.env['mosque.attendance'].sudo().browse(
            int(attendance_id))

        if not attendance.exists():
            return api_response(error='Attendance record not found', status=404)

        if attendance.engineer_id.id != employee.id:
            return api_response(error='Not your attendance record', status=403)

        if attendance.check_out:
            return api_response(error='Already checked out', status=409)

        now = datetime.now()

        # Calculate duration
        duration = (now - attendance.check_in).total_seconds() / 3600

        attendance.write({
            'check_out': now,
        })

        # Check minimum visit duration
        ICP = request.env['ir.config_parameter'].sudo()
        min_minutes = int(ICP.get_param('waqf.mobile.min_visit_minutes', 30))
        is_short = duration * 60 < min_minutes

        return api_response(data={
            'attendance_id': attendance.id,
            'check_in':      str(attendance.check_in),
            'check_out':     str(now),
            'duration_hrs':  round(duration, 2),
            'duration_label': _format_duration(duration),
            'is_validated':  attendance.is_validated,
            'auto_triggered': auto_triggered,
            'short_visit':   is_short,
            'short_warning':  ('زيارة قصيرة — أقل من %d دقيقة' % min_minutes)
                              if is_short else None,
        })

    # ── GET /api/waqf/attendance/active ──────────────────────────
    @http.route('/api/waqf/attendance/active',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def active_checkin(self, employee=None, **kwargs):
        """
        Check if employee has an active check-in anywhere.
        Called on app startup to restore state.
        """
        active = request.env['mosque.attendance'].sudo().search([
            ('engineer_id', '=', employee.id),
            ('check_out',   '=', False),
        ], order='check_in desc', limit=1)

        if not active:
            return api_response(data={'active': False})

        from datetime import datetime
        elapsed = (datetime.now() - active.check_in).total_seconds() / 3600

        # Check long stay alert
        ICP = request.env['ir.config_parameter'].sudo()
        max_hours = int(ICP.get_param('waqf.mobile.long_stay_hours', 8))
        long_stay = elapsed > max_hours

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
            'long_stay_alert': long_stay,
        })

    # ── GET /api/waqf/attendance/history ─────────────────────────
    @http.route('/api/waqf/attendance/history',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def history(self, employee=None, **kwargs):
        """
        Visit history for this employee.
        Query params: mosque_id (optional), days (default 30)
        """
        mosque_id = request.httprequest.args.get('mosque_id')
        days      = int(request.httprequest.args.get('days', 30))

        from datetime import datetime, timedelta
        since = datetime.now() - timedelta(days=days)

        domain = [
            ('engineer_id', '=', employee.id),
            ('check_in',    '>=', since),
        ]
        if mosque_id:
            domain.append(('mosque_id', '=', int(mosque_id)))

        visits = request.env['mosque.attendance'].sudo().search(
            domain, order='check_in desc', limit=100)

        result = []
        for v in visits:
            result.append({
                'id':          v.id,
                'mosque_id':   v.mosque_id.id,
                'mosque_name': v.mosque_id.name,
                'mosque_code': v.mosque_id.code,
                'check_in':    str(v.check_in),
                'check_out':   str(v.check_out) if v.check_out else None,
                'duration':    v.duration,
                'duration_label': _format_duration(v.duration),
                'is_validated': v.is_validated,
                'distance_m':  v.distance_m,
            })

        return api_response(data={
            'visits': result,
            'total':  len(result),
            'days':   days,
        })


def _format_duration(hours):
    if not hours:
        return '0 دقيقة'
    h = int(hours)
    m = int((hours - h) * 60)
    if h == 0:
        return '%d دقيقة' % m
    if m == 0:
        return '%d ساعة' % h
    return '%d ساعة %d دقيقة' % (h, m)
