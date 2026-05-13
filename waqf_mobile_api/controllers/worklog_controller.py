from odoo import http
from odoo.http import request
from .base import api_response, require_token, get_json_body
import base64


class WaqfWorkLogController(http.Controller):

    # ── GET /api/waqf/worklogs/pending ───────────────────────────
    @http.route('/api/waqf/worklogs/pending',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def pending_worklogs(self, employee=None, **kwargs):
        """
        All submitted work logs across assigned mosques awaiting approval.
        Query params: mosque_id (optional filter)
        """
        mosque_id = request.httprequest.args.get('mosque_id')
        mosque_ids = employee.all_mosque_ids.ids

        domain = [
            ('mosque_id', 'in', mosque_ids),
            ('state',     '=', 'submitted'),
        ]
        if mosque_id:
            domain.append(('mosque_id', '=', int(mosque_id)))

        logs = request.env['contractor.work.log'].sudo().search(
            domain, order='log_date desc')

        result = []
        for lg in logs:
            # Get photo URLs
            photos = []
            for att in lg.photo_ids:
                photos.append({
                    'id':   att.id,
                    'name': att.name,
                    'url':  '/web/image/%d' % att.id,
                    'mimetype': att.mimetype,
                })

            result.append({
                'id':             lg.id,
                'name':           lg.name,
                'mosque_id':      lg.mosque_id.id,
                'mosque_name':    lg.mosque_id.name,
                'mosque_code':    lg.mosque_id.code,
                'supervisor':     lg.supervisor_id.name if lg.supervisor_id else '',
                'boq_code':       lg.boq_id.item_code if lg.boq_id else '',
                'boq_description': lg.boq_id.description if lg.boq_id else '',
                'qty_executed':   lg.qty_executed,
                'uom':            lg.uom or '',
                'unit_price':     lg.unit_price,
                'line_value':     lg.line_value,
                'location':       lg.location_detail or '',
                'log_date':       str(lg.log_date),
                'photos':         photos,
                'photo_count':    lg.photo_count,
                'subtask_id':     lg.subtask_id.id if lg.subtask_id else None,
                'task_name':      lg.task_id.name if lg.task_id else '',
            })

        return api_response(data={
            'pending': result,
            'total':   len(result),
        })

    # ── GET /api/waqf/worklogs/<id>/photos ───────────────────────
    @http.route('/api/waqf/worklogs/<int:log_id>/photos',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def worklog_photos(self, log_id, employee=None, **kwargs):
        """Get base64 encoded photos for a work log."""
        log = request.env['contractor.work.log'].sudo().browse(log_id)
        if not log.exists():
            return api_response(error='Work log not found', status=404)

        # Access check
        if log.mosque_id not in employee.all_mosque_ids:
            return api_response(error='Access denied', status=403)

        photos = []
        for att in log.photo_ids:
            photos.append({
                'id':       att.id,
                'name':     att.name,
                'mimetype': att.mimetype,
                'url':      '/web/image/%d' % att.id,
                'size':     att.file_size,
            })

        return api_response(data={'photos': photos})

    # ── POST /api/waqf/worklogs/<id>/approve ─────────────────────
    @http.route('/api/waqf/worklogs/<int:log_id>/approve',
                type='http', auth='none', methods=['POST'], csrf=False)
    @require_token
    def approve_worklog(self, log_id, employee=None, **kwargs):
        """
        Approve a work log — updates BOQ qty and subtask state.

        Request: {} (empty body — no extra data needed)

        Response:
        {
            "approved": true,
            "log_id": 45,
            "subtask_updated": true
        }
        """
        log = request.env['contractor.work.log'].sudo().browse(log_id)
        if not log.exists():
            return api_response(error='Work log not found', status=404)

        if log.mosque_id not in employee.all_mosque_ids:
            return api_response(error='Access denied', status=403)

        if log.state != 'submitted':
            return api_response(
                error='Work log is not in submitted state (current: %s)' % log.state,
                status=409)

        log.action_approve()

        # Update subtask review_state if linked
        subtask_updated = False
        if log.subtask_id:
            log.subtask_id.sudo().write({
                'review_state': 'approved',
                'approved_by':  employee.user_id.id,
            })
            # Check if parent task is now all green
            if log.subtask_id.parent_id:
                log.subtask_id._check_and_promote_parent()
            subtask_updated = True

        return api_response(data={
            'approved':        True,
            'log_id':          log_id,
            'new_state':       log.state,
            'boq_executed_qty': log.boq_id.executed_qty if log.boq_id else 0,
            'subtask_updated': subtask_updated,
        })

    # ── POST /api/waqf/worklogs/<id>/reject ──────────────────────
    @http.route('/api/waqf/worklogs/<int:log_id>/reject',
                type='http', auth='none', methods=['POST'], csrf=False)
    @require_token
    def reject_worklog(self, log_id, employee=None, **kwargs):
        """
        Reject a work log with mandatory reason.

        Request:
        {
            "reason": "الصورة لا تُظهر العمل بوضوح — أعد التصوير"
        }
        """
        body   = get_json_body()
        reason = body.get('reason', '').strip()

        if not reason:
            return api_response(
                error='Rejection reason is required', status=400)

        log = request.env['contractor.work.log'].sudo().browse(log_id)
        if not log.exists():
            return api_response(error='Work log not found', status=404)

        if log.mosque_id not in employee.all_mosque_ids:
            return api_response(error='Access denied', status=403)

        if log.state != 'submitted':
            return api_response(
                error='Work log is not in submitted state', status=409)

        # Reject + set reason
        log.write({
            'state':         'rejected',
            'reject_reason': reason,
        })

        # Reverse BOQ qty
        if log.boq_id:
            log.boq_id.executed_qty = max(
                0, log.boq_id.executed_qty - log.qty_executed)

        # Update subtask
        if log.subtask_id:
            log.subtask_id.sudo().write({
                'review_state':   'rejected',
                'rejection_note': reason,
            })

        # Notify supervisor via chatter
        log.message_post(
            body='❌ رفض الاستشاري <b>%s</b> هذا العمل.<br/>'
                 '<b>السبب:</b> %s' % (employee.name, reason))

        return api_response(data={
            'rejected': True,
            'log_id':   log_id,
            'reason':   reason,
        })
