from odoo import http
from odoo.http import request
from .base import api_response, require_token, get_json_body
import base64
from datetime import date
import logging

_logger = logging.getLogger(__name__)


class WaqfSupervisionController(http.Controller):

    # ── GET /api/waqf/supervision/workforce-types ─────────────────
    @http.route('/api/waqf/supervision/workforce-types',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def workforce_types(self, employee=None, **kwargs):
        """قائمة أنواع العمالة والمعدات للاختيار منها في التطبيق."""
        types = request.env['mosque.workforce.type'].sudo().search(
            [('active', '=', True)], order='category, sequence')

        manpower = []
        equipment = []
        for t in types:
            item = {'id': t.id, 'name': t.name}
            if t.category == 'manpower':
                manpower.append(item)
            else:
                equipment.append(item)

        return api_response(data={
            'manpower': manpower,
            'equipment': equipment,
        })

    # ── POST /api/waqf/supervision/submit ────────────────────────
    # ── POST /api/waqf/supervision/submit ─────────────────────────
    @http.route('/api/waqf/supervision/submit',
                type='http', auth='none', methods=['POST'], csrf=False)
    @require_token
    def submit_report(self, employee=None, **kwargs):
        body = get_json_body()
        portal_user = kwargs.get('portal_user')
        mosque_id = body.get('mosque_id')
        attendance_id = body.get('attendance_id')

        if not mosque_id:
            return api_response(error='mosque_id is required', status=400)

        mosque = request.env['mosque.mosque'].sudo().browse(int(mosque_id))
        if not mosque.exists():
            return api_response(error='Mosque not found', status=404)

        # تحقق من الصلاحية
        if employee and mosque not in employee.all_mosque_ids:
            return api_response(error='Access denied', status=403)
        if portal_user and mosque not in portal_user.effective_mosque_ids:
            return api_response(error='Access denied', status=403)

        # GPS من سجل الحضور
        gps_lat = gps_lng = 0.0
        gps_valid = within_fence = False
        if attendance_id:
            att = request.env['mosque.attendance'].sudo().browse(int(attendance_id))
            if att.exists():
                gps_lat = att.gps_latitude
                gps_lng = att.gps_longitude
                gps_valid = att.gps_validated
                within_fence = att.is_validated

        # engineer_id
        engineer_id = portal_user.user_id.id

        _logger.info("**************************************")
        _logger.info("portal_user = %s", portal_user)
        _logger.info("request.env.user = %s", request.env.user)
        _logger.info("request.env.user.id = %s", request.env.user.id)
        _logger.info("engineer_id = %s", engineer_id)
        _logger.info("**************************************")

        sup_vals = {
            'mosque_id': mosque.id,
            'engineer_id': engineer_id,
            'report_date': date.today(),
            'report_type': body.get('report_type', 'daily'),
            'state': 'submitted',
            'weather': body.get('weather', 'sunny'),
            'workers_on_site': int(body.get('workers_on_site', 0)),
            'activities_done': body.get('activities_done', ''),
            'activities_planned': body.get('activities_planned', ''),
            'issues': body.get('issues', ''),
            'recommendations': body.get('recommendations', ''),
            'ncr_count': int(body.get('ncr_count', 0)),
            'safety_incidents': int(body.get('safety_incidents', 0)),
            'itp_hold_points_checked': int(body.get('itp_checked', 0)),
            'itp_hold_points_approved': int(body.get('itp_approved', 0)),
            'gps_latitude': gps_lat,
            'gps_longitude': gps_lng,
            'gps_validated': gps_valid,
            'qr_validated': within_fence,
        }

        supervision = request.env['mosque.supervision'].sudo().create(sup_vals)

        # ── العمالة والمعدات ───────────────────────────────────────
        # Request format:
        # "workforce": [
        #   {"type_id": 1, "count": 3},
        #   {"type_id": 5, "count": 1}
        # ]
        Workforce = request.env['mosque.supervision.workforce'].sudo()
        workforce_created = 0
        for item in body.get('workforce', []):
            type_id = item.get('type_id')
            count = int(item.get('count', 0))
            if type_id and count > 0:
                Workforce.create({
                    'supervision_id': supervision.id,
                    'type_id': int(type_id),
                    'count': count,
                })
                workforce_created += 1

        # ── الصور ─────────────────────────────────────────────────
        photos_attached = 0
        Attachment = request.env['ir.attachment'].sudo()
        for photo in body.get('photos', []):
            try:
                att = Attachment.create({
                    'name': photo.get('name', 'photo.jpg'),
                    'datas': photo.get('data', ''),
                    'mimetype': photo.get('mimetype', 'image/jpeg'),
                    'res_model': 'mosque.supervision',
                    'res_id': supervision.id,
                })
                supervision.photo_ids = [(4, att.id)]
                photos_attached += 1
            except Exception:
                pass

        # ── Chatter ────────────────────────────────────────────────
        author_id = False

        if portal_user and portal_user.user_id:
            author_id = portal_user.user_id.partner_id.id

        supervision.sudo().with_context(
            mail_create_nosubscribe=True,
            mail_notrack=True,
        ).message_post(
            body=f'تقرير مرفوع من التطبيق بواسطة {reporter}',
            message_type='comment',
            subtype_xmlid='mail.mt_note',
            author_id=author_id,
        )

        return api_response(data={
            'supervision_id': supervision.id,
            'reference': supervision.name,
            'mosque': mosque.name,
            'report_type': supervision.report_type,
            'report_date': str(supervision.report_date),
            'state': supervision.state,
            'photos_attached': photos_attached,
            'workforce_added': workforce_created,
            'gps_validated': gps_valid,
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
        limit = int(request.httprequest.args.get('limit', 20))

        domain = [('engineer_id', '=', employee.id)]
        if mosque_id:
            domain.append(('mosque_id', '=', int(mosque_id)))

        reports = request.env['mosque.supervision'].sudo().search(
            domain, order='report_date desc', limit=limit)

        result = [{
            'id': r.id,
            'reference': r.name,
            'mosque': r.mosque_id.name,
            'mosque_code': r.mosque_id.code,
            'date': str(r.report_date),
            'type': r.report_type,
            'state': r.state,
            'workers': r.workers_on_site,
            'ncr': r.ncr_count,
            'photo_count': len(r.photo_ids),
        } for r in reports]

        return api_response(data={'reports': result, 'total': len(result)})
