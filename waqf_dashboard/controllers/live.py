# -*- coding: utf-8 -*-
# controllers/live_wall.py
from odoo import http
from odoo.http import request


class LiveWallController(http.Controller):

    @http.route('/live/wall', type='http', auth='user', website=True)
    def live_wall(self, **kw):
        """جدار البثوث المباشرة — حتى 9 بثوث نشطة."""
        streams = request.env['waqf.live.stream'].sudo().search([
            # ('is_active', '=', True),
            ('stream_url', '!=', False),
        ], limit=9, order='start_time desc')

        return request.render('waqf_dashboard.tmpl_live_wall', {
            'streams': streams,
        })

    @http.route('/live/wall/data', type='json', auth='user')
    def live_wall_data(self, **kw):
        """تحديث دوري لحالة البثوث (بدون إعادة تحميل الصفحة)."""
        streams = request.env['waqf.live.stream'].sudo().search([
            # ('is_active', '=', True),
            ('stream_url', '!=', False),
        ], limit=9, order='start_time desc')

        return [{
            'id':      s.id,
            'name':    s.name or '',
            'mosque':  s.mosque_id.name or '',
            'city':    s.mosque_id.city or '',
            'url':     s.stream_url or '',
            'viewers': s.viewers or 0,
            'start':   str(s.start_time or '')[:16],
        } for s in streams]