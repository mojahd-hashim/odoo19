# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import api, fields, models


class WaqfAiMosqueSnapshot(models.Model):
    _name = 'waqf.ai.mosque.snapshot'
    _description = 'AI Mosque Snapshot'
    _order = 'run_id desc, mosque_id'

    run_id = fields.Many2one('waqf.ai.snapshot.run', required=True, ondelete='cascade', index=True)
    phase_id = fields.Many2one('mosque.package', index=True)
    mosque_id = fields.Many2one('mosque.mosque', required=True, index=True)
    mosque_name = fields.Char()
    mosque_code = fields.Char()
    contractor = fields.Char(index=True)
    state = fields.Char(index=True)
    contract_value = fields.Float()
    planned_start = fields.Date()
    planned_end = fields.Date()
    financial_progress = fields.Float()
    time_progress = fields.Float()
    visit_compliance = fields.Float()
    overall_kpi = fields.Float()
    certified_amount = fields.Float()
    total_boq_value = fields.Float()
    change_order_value = fields.Float()
    days_delay = fields.Integer()
    pending_certificates_count = fields.Integer()
    pending_certificates_value = fields.Float()
    oldest_pending_certificate_days = fields.Integer()
    change_orders_count = fields.Integer()
    pending_change_orders_count = fields.Integer()
    change_orders_value = fields.Float()
    supervision_reports_count = fields.Integer()
    last_supervision_report_date = fields.Date()
    days_since_last_report = fields.Integer()
    attendance_count_7d = fields.Integer()
    validated_visits_7d = fields.Integer()
    visit_hours_7d = fields.Float()
    active_live_stream_count = fields.Integer()
    workers_latest = fields.Integer()
    equipment_latest = fields.Integer()
    ncr_count_30d = fields.Integer()
    safety_incidents_30d = fields.Integer()
    boq_execution_value = fields.Float()
    boq_contract_value = fields.Float()
    boq_execution_percent = fields.Float()
    rejected_tasks_count = fields.Integer()
    blocked_tasks_count = fields.Integer()
    overdue_tasks_count = fields.Integer()
    numeric_snapshot_json = fields.Json()
    text_snapshot_json = fields.Json()

    @api.model
    def _safe_num(self, value):
        return float(value or 0.0)

    @api.model
    def _prepare_snapshot_values(self, run, phase, mosque):
        today = fields.Date.context_today(self)
        dt_now = fields.Datetime.now()
        d7 = dt_now - timedelta(days=7)
        d30 = dt_now - timedelta(days=30)

        certificates = getattr(mosque, 'certificate_ids', self.env['mosque.certificate']).sudo()
        pending_certs = certificates.filtered(lambda c: getattr(c, 'state', False) not in ('done', 'approved', 'paid', 'cancel'))
        oldest_pending_days = 0
        if pending_certs:
            oldest = min(pending_certs.mapped('create_date') or [dt_now])
            oldest_pending_days = (dt_now.date() - oldest.date()).days

        cos = getattr(mosque, 'change_order_ids', self.env['mosque.change.order']).sudo()
        pending_cos = cos.filtered(lambda c: getattr(c, 'state', False) not in ('approved', 'done', 'cancel', 'rejected'))

        reports = getattr(mosque, 'supervision_ids', self.env['mosque.supervision']).sudo().sorted('report_date')
        reports_30d = reports.filtered(lambda r: getattr(r, 'report_date', False) and fields.Date.to_date(r.report_date) >= (today - timedelta(days=30)))
        last_report = reports[-1] if reports else False
        last_report_date = getattr(last_report, 'report_date', False) if last_report else False
        days_since_last_report = (today - fields.Date.to_date(last_report_date)).days if last_report_date else 999

        attendance = getattr(mosque, 'attendance_ids', self.env['mosque.attendance']).sudo()
        attendance_7d = attendance.filtered(lambda a: getattr(a, 'check_in', False) and a.check_in >= d7)
        validated_7d = attendance_7d.filtered(lambda a: bool(getattr(a, 'is_validated', False) or getattr(a, 'gps_validated', False) or getattr(a, 'qr_validated', False)))
        short_visits = attendance_7d.filtered(lambda a: self._safe_num(getattr(a, 'duration', 0)) and self._safe_num(a.duration) < 0.25)

        boq_lines = getattr(mosque, 'boq_ids', self.env['mosque.boq']).sudo()
        boq_contract_value = sum(self._safe_num(getattr(b, 'contracted_qty', 0)) * self._safe_num(getattr(b, 'unit_price', 0)) for b in boq_lines)
        boq_execution_value = sum(self._safe_num(getattr(b, 'executed_qty', 0)) * self._safe_num(getattr(b, 'unit_price', 0)) for b in boq_lines)
        boq_execution_percent = (boq_execution_value / boq_contract_value * 100.0) if boq_contract_value else 0.0

        Task = self.env['project.task'].sudo()
        tasks = Task.search([('mosque_id', '=', mosque.id)]) if 'mosque_id' in Task._fields else Task.browse()
        rejected_tasks = tasks.filtered(lambda t: getattr(t, 'review_state', False) in ('rejected', 'reject'))
        blocked_tasks = tasks.filtered(lambda t: bool(getattr(t, 'is_blocked_by_co', False) or getattr(t, 'blocking_co_id', False)))
        overdue_tasks = tasks.filtered(lambda t: getattr(t, 'date_deadline', False) and t.date_deadline < today and getattr(t, 'stage_id', False))

        latest_workers = int(getattr(last_report, 'workers_on_site', 0) or 0) if last_report else 0
        latest_equipment = int(getattr(last_report, 'equipment_count', 0) or 0) if last_report else 0
        ncr_30 = sum(int(getattr(r, 'ncr_count', 0) or 0) for r in reports_30d)
        safety_30 = sum(int(getattr(r, 'safety_incidents', 0) or 0) for r in reports_30d)

        active_streams = len(reports.filtered(lambda r: bool(getattr(r, 'live_stream_url', False)))) + len(attendance_7d.filtered(lambda a: bool(getattr(a, 'live_stream_url', False))))
        financial_progress = self._safe_num(getattr(mosque, 'financial_progress', 0))
        time_progress = self._safe_num(getattr(mosque, 'time_progress', 0))
        days_delay = int(getattr(mosque, 'days_delay', 0) or 0)

        report_quality_score = self._report_quality_score(last_report, boq_lines)
        numeric = {
            'financial_time_variance': financial_progress - time_progress,
            'report_quality_score': report_quality_score,
            'short_visits_7d': len(short_visits),
            'expected_finish_delay': days_delay if days_delay > 0 else 0,
            'near_phase_end': bool(getattr(phase, 'planned_end', False) and (fields.Date.to_date(phase.planned_end) - today).days <= 14),
        }
        text = {
            'latest_issues': self._truncate(getattr(last_report, 'issues', '') if last_report else ''),
            'latest_recommendations': self._truncate(getattr(last_report, 'recommendations', '') if last_report else ''),
            'latest_activities_done': self._truncate(getattr(last_report, 'activities_done', '') if last_report else ''),
            'latest_activities_planned': self._truncate(getattr(last_report, 'activities_planned', '') if last_report else ''),
            'attendance_notes': self._truncate(' | '.join(attendance_7d.mapped('notes')[:5])) if attendance_7d else '',
        }
        vals = {
            'run_id': run.id,
            'phase_id': phase.id,
            'mosque_id': mosque.id,
            'mosque_name': getattr(mosque, 'name', False),
            'mosque_code': getattr(mosque, 'code', False),
            'contractor': getattr(getattr(mosque, 'contractor', False), 'display_name', False) or str(getattr(mosque, 'contractor', '') or ''),
            'state': getattr(mosque, 'state', False),
            'contract_value': self._safe_num(getattr(mosque, 'contract_value', 0)),
            'planned_start': getattr(mosque, 'planned_start', False),
            'planned_end': getattr(mosque, 'planned_end', False),
            'financial_progress': financial_progress,
            'time_progress': time_progress,
            'visit_compliance': self._safe_num(getattr(mosque, 'visit_compliance', 0)),
            'overall_kpi': self._safe_num(getattr(mosque, 'overall_kpi', 0)),
            'certified_amount': self._safe_num(getattr(mosque, 'certified_amount', 0)),
            'total_boq_value': self._safe_num(getattr(mosque, 'total_boq_value', 0)),
            'change_order_value': self._safe_num(getattr(mosque, 'change_order_value', 0)),
            'days_delay': days_delay,
            'pending_certificates_count': len(pending_certs),
            'pending_certificates_value': sum(self._safe_num(getattr(c, 'certified_amount', 0)) for c in pending_certs),
            'oldest_pending_certificate_days': oldest_pending_days,
            'change_orders_count': len(cos),
            'pending_change_orders_count': len(pending_cos),
            'change_orders_value': sum(self._safe_num(getattr(c, 'amount', 0)) for c in cos),
            'supervision_reports_count': len(reports),
            'last_supervision_report_date': last_report_date,
            'days_since_last_report': days_since_last_report,
            'attendance_count_7d': len(attendance_7d),
            'validated_visits_7d': len(validated_7d),
            'visit_hours_7d': sum(self._safe_num(getattr(a, 'duration', 0)) for a in attendance_7d),
            'active_live_stream_count': active_streams,
            'workers_latest': latest_workers,
            'equipment_latest': latest_equipment,
            'ncr_count_30d': ncr_30,
            'safety_incidents_30d': safety_30,
            'boq_execution_value': boq_execution_value,
            'boq_contract_value': boq_contract_value,
            'boq_execution_percent': boq_execution_percent,
            'rejected_tasks_count': len(rejected_tasks),
            'blocked_tasks_count': len(blocked_tasks),
            'overdue_tasks_count': len(overdue_tasks),
            'numeric_snapshot_json': numeric,
            'text_snapshot_json': text,
        }
        payload = dict(vals)
        payload.update({'run_id': run.id, 'phase_id': phase.id, 'mosque_id': mosque.id})
        return vals, payload

    @api.model
    def _report_quality_score(self, report, boq_lines):
        if not report:
            return 0
        score = 0
        checks = ['activities_done', 'issues', 'recommendations']
        score += sum(15 for c in checks if getattr(report, c, False))
        score += 15 if getattr(report, 'photo_ids', False) else 0
        score += 15 if getattr(report, 'gps_validated', False) else 0
        score += 10 if getattr(report, 'qr_validated', False) else 0
        score += 15 if boq_lines else 0
        return min(score, 100)

    @api.model
    def _truncate(self, text, limit=900):
        text = text or ''
        return text[:limit]
