from odoo import http
from odoo.http import request
from .base import api_response, require_token


class WaqfSettingsController(http.Controller):

    # ── GET /api/waqf/settings ────────────────────────────────────
    @http.route('/api/waqf/settings',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def get_settings(self, employee=None, **kwargs):
        config   = request.env['res.config.settings'].sudo().get_mobile_config()
        base_url = request.env['ir.config_parameter'].sudo().get_param(
            'web.base.url', '')
        config['server'] = {
            'base_url':    base_url,
            'api_version': '1.0',
            'db':          request.env.cr.dbname,
        }
        return api_response(data=config)

    # ── GET /api/waqf/settings/mosques-geofence ───────────────────
    @http.route('/api/waqf/settings/mosques-geofence',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def mosques_geofence(self, employee=None, **kwargs):
        portal_user = kwargs.get('portal_user')

        if employee:
            mosques = employee.all_mosque_ids
        elif portal_user:
            mosques = portal_user.effective_mosque_ids
        else:
            return api_response(error='Unauthorized', status=401)

        result = [{
            'id':      m.id,
            'code':    m.code,
            'name':    m.name,
            'lat':     m.latitude,
            'lng':     m.longitude,
            'radius':  m.geofence_radius or 100,
            'qr_code': m.qr_code or '',
        } for m in mosques if m.latitude and m.longitude]

        return api_response(data={'geofences': result, 'total': len(result)})