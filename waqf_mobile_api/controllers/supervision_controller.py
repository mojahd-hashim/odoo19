from odoo import http
from odoo.http import request
from .base import api_response, require_token, get_json_body
import base64
from datetime import date


class WaqfSupervisionController(http.Controller):

    # ── POST /api/waqf/supervision/submit ────────────────────────
    @http.route('/api/waqf/supervision/submit',
                type='http', auth='none', methods=['POST'], csrf=False)
    @require_token
    def submit_report(self, employee=None, **kwargs):
        """
        Submit a supervision report from mobile.

        Request:
        {
            "mosque_id": 12,
            "attendance_id": 45,       (links report to visit)
            "report_type": "daily",
            "weather": "sunny",
            "workers_on_site": 12,
            "equipment_count": 3,
            "activities_done": "...",
            "issues": "...",           (optional)
            "ncr_count": 0,
            "safety_incidents": 0,
            "itp_checked": 2,
            "itp_approved": 2,
            "photos": [                (optional — base64 images)
                {
                    "name": "site_photo_1.jpg",
                    "data": "base64...",
                    "mimetype": "image/jpeg"
                }
            ]
        }
        """
        body          = get_json_body()
        mosque_id     = body.get('mosque_id')
        attendance_id = body.get('attendance_id')

        if not mosque_id:
            return api_response(error='mosque_id is required', status=400)

        mosque = request.env['mosque.mosque'].sudo().browse(int(mosque_id))
        if not mosque.exists():
            return api_response(error='Mosque not found', status=404)

        if mosque not in employee.all_mosque_ids:
            return api_response(error='Access denied', status=403)

        # Get GPS from attendance record
        gps_lat, gps_lng, gps_valid, within_fence = 0.0, 0.0, False, False
        if attendance_id:
            att = request.env['mosque.attendance'].sudo().browse(
                int(attendance_id))
            if att.exists() and att.engineer_id.id == employee.id:
                gps_lat     = att.gps_latitude
                gps_lng     = att.gps_longitude
                gps_valid   = att.gps_validated
                within_fence = att.is_validated

        # Create supervision report
        sup_vals = {
            'mosque_id':    mosque.id,
            'engineer_id':  employee.id,
            'report_date':  date.today(),
            'report_type':  body.get('report_type', 'daily'),
            'state':        'submitted',
            'weather':      body.get('weather', 'sunny'),
            'workers_on_site':           int(body.get('workers_on_site', 0)),
            'equipment_count':           int(body.get('equipment_count', 0)),
            'activities_done':           body.get('activities_done', ''),
            'activities_planned':        body.get('activities_planned', ''),
            'issues':                    body.get('issues', ''),
            'recommendations':           body.get('recommendations', ''),
            'ncr_count':                 int(body.get('ncr_count', 0)),
            'safety_incidents':          int(body.get('safety_incidents', 0)),
            'itp_hold_points_checked':   int(body.get('itp_checked', 0)),
            'itp_hold_points_approved':  int(body.get('itp_approved', 0)),
            'gps_latitude':  gps_lat,
            'gps_longitude': gps_lng,
            'gps_validated': gps_valid,
            'qr_validated':  within_fence,
        }

        supervision = request.env['mosque.supervision'].sudo().create(sup_vals)

        # Attach photos
        photos_attached = 0
        Attachment = request.env['ir.attachment'].sudo()
        for photo in body.get('photos', []):
            try:
                att = Attachment.create({
                    'name':      photo.get('name', 'photo.jpg'),
                    'datas':     photo.get('data', ''),
                    'mimetype':  photo.get('mimetype', 'image/jpeg'),
                    'res_model': 'mosque.supervision',
                    'res_id':    supervision.id,
                })
                supervision.photo_ids = [(4, att.id)]
                photos_attached += 1
            except Exception:
                pass

        # Post chatter message
        supervision.message_post(
            body='📱 تقرير مُرسَل من تطبيق الجوال بواسطة %s' % employee.name)

        return api_response(data={
            'supervision_id':  supervision.id,
            'reference':       supervision.name,
            'mosque':          mosque.name,
            'report_type':     supervision.report_type,
            'report_date':     str(supervision.report_date),
            'state':           supervision.state,
            'photos_attached': photos_attached,
            'gps_validated':   gps_valid,
        })

    # ── GET /api/waqf/supervision/history ────────────────────────
    @http.route('/api/waqf/supervision/history',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def report_history(self, employee=None, **kwargs):
        """
        Recent supervision reports by this employee.
        Query params: mosque_id (optional), limit (default 20)
        """
        mosque_id = request.httprequest.args.get('mosque_id')
        limit     = int(request.httprequest.args.get('limit', 20))

        domain = [('engineer_id', '=', employee.id)]
        if mosque_id:
            domain.append(('mosque_id', '=', int(mosque_id)))

        reports = request.env['mosque.supervision'].sudo().search(
            domain, order='report_date desc', limit=limit)

        result = [{
            'id':          r.id,
            'reference':   r.name,
            'mosque':      r.mosque_id.name,
            'mosque_code': r.mosque_id.code,
            'date':        str(r.report_date),
            'type':        r.report_type,
            'state':       r.state,
            'workers':     r.workers_on_site,
            'ncr':         r.ncr_count,
            'photo_count': len(r.photo_ids),
        } for r in reports]

        return api_response(data={'reports': result, 'total': len(result)})
