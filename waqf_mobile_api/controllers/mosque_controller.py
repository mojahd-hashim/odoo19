from odoo import http
from odoo.http import request
from .base import api_response, require_token


class WaqfMosqueController(http.Controller):

    # ── GET /api/waqf/mosques ─────────────────────────────────────
    @http.route('/api/waqf/mosques',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def list_mosques(self, employee=None, **kwargs):
        """
        List all mosques assigned to this consultant.
        Response includes geofence config + today's visit status.
        """
        from datetime import date
        today = date.today()

        mosques = employee.all_mosque_ids.sorted('code')
        Attendance = request.env['mosque.attendance'].sudo()

        result = []
        for m in mosques:
            # Today's visit
            today_visits = Attendance.search([
                ('mosque_id',   '=', m.id),
                ('engineer_id', '=', employee.id),
                ('check_in',    '>=', str(today) + ' 00:00:00'),
            ], order='check_in desc', limit=1)

            visit_status = 'not_visited'
            active_checkin_id = None
            if today_visits:
                v = today_visits[0]
                if v.check_out:
                    visit_status = 'completed'
                else:
                    visit_status = 'checked_in'
                    active_checkin_id = v.id

            # Pending work logs count
            pending_logs = request.env['contractor.work.log'].sudo().search_count([
                ('mosque_id', '=', m.id),
                ('state',     '=', 'submitted'),
            ])

            result.append({
                'id':               m.id,
                'code':             m.code,
                'name':             m.name,
                'city':             m.city,
                'district':         m.district or '',
                'state':            m.state,
                'state_label':      _state_label(m.state),
                'lat':              m.latitude,
                'lng':              m.longitude,
                'geofence_radius':  m.geofence_radius or 100,
                'qr_code':          m.qr_code or '',
                'planned_end':      str(m.planned_end) if m.planned_end else '',
                'days_delay':       m.days_delay,
                'financial_pct':    round(m.financial_progress, 1),
                'overall_kpi':      round(m.overall_kpi, 1),
                'visit_today':      visit_status,
                'active_checkin_id': active_checkin_id,
                'pending_worklogs': pending_logs,
                'package':          m.package_id.name if m.package_id else '',
            })

        return api_response(data={'mosques': result, 'total': len(result)})

    # ── GET /api/waqf/mosques/<id> ────────────────────────────────
    @http.route('/api/waqf/mosques/<int:mosque_id>',
                type='http', auth='none', methods=['GET'], csrf=False)
    @require_token
    def mosque_detail(self, mosque_id, employee=None, **kwargs):
        """
        Full mosque detail including:
        - Geofence config
        - Active tasks summary
        - Pending work logs count
        - Last 5 visits
        """
        mosque = request.env['mosque.mosque'].sudo().browse(mosque_id)
        if not mosque.exists():
            return api_response(error='Mosque not found', status=404)

        # Verify access
        if mosque not in employee.all_mosque_ids:
            return api_response(error='Access denied to this mosque', status=403)

        # Tasks summary
        tasks = []
        if mosque.project_id:
            task_records = request.env['project.task'].sudo().search([
                ('project_id', '=', mosque.project_id.id),
                ('parent_id',  '=', False),
                ('stage_id.is_closed', '=', False),
            ], order='date_deadline asc')

            for t in task_records:
                pending_subs = len(t.child_ids.filtered(
                    lambda s: s.review_state == 'submitted'))
                tasks.append({
                    'id':            t.id,
                    'name':          t.name,
                    'stage':         t.stage_id.name if t.stage_id else '',
                    'waqf_stage':    t.stage_id.waqf_stage if t.stage_id else '',
                    'kanban_color':  t.kanban_color,
                    'deadline':      str(t.date_deadline) if t.date_deadline else '',
                    'review_state':  t.review_state,
                    'pending_subs':  pending_subs,
                    'subtask_count': len(t.child_ids),
                    'all_green':     t.subtasks_all_green,
                })

        # Pending work logs
        pending_logs = request.env['contractor.work.log'].sudo().search([
            ('mosque_id', '=', mosque_id),
            ('state',     '=', 'submitted'),
        ], order='log_date desc')

        logs_data = [{
            'id':           lg.id,
            'name':         lg.name,
            'boq_code':     lg.boq_id.item_code if lg.boq_id else '',
            'boq_desc':     lg.boq_id.description[:50] if lg.boq_id else '',
            'qty':          lg.qty_executed,
            'uom':          lg.uom or '',
            'value':        lg.line_value,
            'date':         str(lg.log_date),
            'photo_count':  lg.photo_count,
            'supervisor':   lg.supervisor_id.name if lg.supervisor_id else '',
        } for lg in pending_logs]

        # Last 5 visits by this employee
        visits = request.env['mosque.attendance'].sudo().search([
            ('mosque_id',   '=', mosque_id),
            ('engineer_id', '=', employee.id),
        ], order='check_in desc', limit=5)

        visits_data = [{
            'id':       v.id,
            'check_in': str(v.check_in),
            'check_out': str(v.check_out) if v.check_out else None,
            'duration':  v.duration,
            'validated': v.is_validated,
        } for v in visits]

        return api_response(data={
            'mosque': {
                'id':              mosque.id,
                'code':            mosque.code,
                'name':            mosque.name,
                'city':            mosque.city,
                'district':        mosque.district or '',
                'state':           mosque.state,
                'lat':             mosque.latitude,
                'lng':             mosque.longitude,
                'geofence_radius': mosque.geofence_radius or 100,
                'qr_code':         mosque.qr_code or '',
                'contract_value':  mosque.contract_value,
                'planned_start':   str(mosque.planned_start) if mosque.planned_start else '',
                'planned_end':     str(mosque.planned_end) if mosque.planned_end else '',
                'financial_pct':   round(mosque.financial_progress, 1),
                'time_pct':        round(mosque.time_progress, 1),
                'visit_pct':       round(mosque.visit_compliance, 1),
                'overall_kpi':     round(mosque.overall_kpi, 1),
                'days_delay':      mosque.days_delay,
                'contractor':      mosque.contractor or '',
            },
            'tasks':         tasks,
            'pending_logs':  logs_data,
            'recent_visits': visits_data,
        })


def _state_label(state):
    labels = {
        'draft':       'لم يبدأ',
        'mobilizing':  'التجهيز',
        'active':      'قيد التنفيذ',
        'initial_hov': 'استلام ابتدائي',
        'final_hov':   'استلام نهائي',
        'warranty':    'فترة الضمان',
        'closed':      'مغلق',
    }
    return labels.get(state, state)
