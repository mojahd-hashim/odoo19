import json
import math
import functools
from odoo import http
from odoo.http import request


def api_response(data=None, error=None, status=200):
    """Standard JSON response wrapper."""
    if error:
        body = {'success': False, 'error': error}
        status = status if status != 200 else 400
    else:
        body = {'success': True, 'data': data}
    return request.make_response(
        json.dumps(body, ensure_ascii=False, default=str),
        headers=[
            ('Content-Type', 'application/json; charset=utf-8'),
            ('Access-Control-Allow-Origin', '*'),
            ('Access-Control-Allow-Methods', 'GET, POST, OPTIONS'),
            ('Access-Control-Allow-Headers',
             'Authorization, Content-Type, X-Idempotency-Key'),
        ],
        status=status,
    )


def require_token(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        auth_header = request.httprequest.headers.get('Authorization', '')
        import logging
        _logger = logging.getLogger(__name__)
        _logger.info('TOKEN PREFIX: %s', auth_header[:30] if auth_header else 'NONE')

        if not auth_header.startswith('Bearer '):
            return api_response(
                error='Missing or invalid Authorization header', status=401)
        raw_token = auth_header[7:]

        # ① توكن موظف داخلي
        employee = request.env['waqf.api.token'].sudo().authenticate(raw_token)
        if employee:
            kwargs['employee'] = employee
            return fn(*args, **kwargs)

        # ② توكن مستخدم بوابة
        import hashlib
        token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
        portal_token = request.env['waqf.portal.token'].sudo().search(
            [('token_hash', '=', token_hash),
             ('is_active',  '=', True)], limit=1)

        if portal_token and portal_token.portal_user_id.is_active:
            kwargs['employee']    = None
            kwargs['portal_user'] = portal_token.portal_user_id
            return fn(*args, **kwargs)

        return api_response(error='Invalid or expired token', status=401)
    return wrapper


def haversine_distance(lat1, lon1, lat2, lon2):
    """Distance in meters between two GPS coordinates."""
    R = 6371000
    lat1, lon1 = math.radians(lat1), math.radians(lon1)
    lat2, lon2 = math.radians(lat2), math.radians(lon2)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    a = math.sin(dlat/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def get_json_body():
    """Parse JSON request body safely."""
    try:
        return json.loads(request.httprequest.data or '{}')
    except Exception:
        return {}
