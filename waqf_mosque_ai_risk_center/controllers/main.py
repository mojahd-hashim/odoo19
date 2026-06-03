# -*- coding: utf-8 -*-
from odoo import http, fields
from odoo.http import request


class WaqfAiRiskController(http.Controller):

    def _current_phase(self):
        return request.env['waqf.ai.snapshot.run'].sudo()._find_current_phase()

    def _alert_payload(self, alert):
        return {
            'id': alert.id,
            'title': alert.title,
            'severity': alert.severity,
            'status': alert.status,
            'alert_type': alert.alert_type,
            'mosque_id': alert.mosque_id.id,
            'mosque_name': alert.mosque_id.display_name if alert.mosque_id else False,
            'contractor': alert.contractor,
            'summary': alert.summary,
            'root_cause': alert.root_cause,
            'impact': alert.impact,
            'phase_impact': alert.phase_impact,
            'recommendation': alert.recommendation,
            'confidence': alert.confidence,
            'priority_score': alert.priority_score,
            'related_metrics': alert.related_metrics_json,
        }

    @http.route('/waqf_ai/alerts/current', type='json', auth='user', methods=['POST'], csrf=False)
    def current_alerts(self, **kwargs):
        phase = self._current_phase()
        domain = []
        if phase:
            domain.append(('phase_id', '=', phase.id))
        alerts = request.env['waqf.ai.alert'].search(domain, order='priority_score desc, create_date desc', limit=int(kwargs.get('limit', 50)))
        return {'phase_id': phase.id if phase else False, 'alerts': [self._alert_payload(a) for a in alerts]}

    @http.route('/waqf_ai/phase/summary', type='json', auth='user', methods=['POST'], csrf=False)
    def phase_summary(self, **kwargs):
        phase = self._current_phase()
        domain = []
        if phase:
            domain.append(('phase_id', '=', phase.id))
        insight = request.env['waqf.ai.phase.insight'].search(domain, order='create_date desc', limit=1)
        if not insight:
            return {'phase_id': phase.id if phase else False, 'summary': False}
        return {
            'phase_id': insight.phase_id.id,
            'phase_health': insight.phase_health,
            'overall_summary': insight.overall_summary,
            'financial_risk_level': insight.financial_risk_level,
            'quality_risk_level': insight.quality_risk_level,
            'supervision_risk_level': insight.supervision_risk_level,
            'approval_risk_level': insight.approval_risk_level,
            'critical_projects_count': insight.critical_projects_count,
            'predicted_delays_count': insight.predicted_delays_count,
            'total_pending_payments': insight.total_pending_payments,
            'total_change_orders_value': insight.total_change_orders_value,
            'total_delay_days': insight.total_delay_days,
            'executive_insights': insight.executive_insights_json,
            'recommendations': insight.recommendations_json,
        }

    @http.route('/waqf_ai/mosque/<int:mosque_id>/risk', type='json', auth='user', methods=['POST'], csrf=False)
    def mosque_risk(self, mosque_id, **kwargs):
        snapshot = request.env['waqf.ai.mosque.snapshot'].search([('mosque_id', '=', mosque_id)], order='create_date desc', limit=1)
        alerts = request.env['waqf.ai.alert'].search([('mosque_id', '=', mosque_id), ('active', '=', True)], order='priority_score desc, create_date desc', limit=20)
        predictions = request.env['waqf.ai.prediction'].search([('mosque_id', '=', mosque_id)], order='create_date desc', limit=10)
        return {
            'snapshot': snapshot.read()[0] if snapshot else False,
            'alerts': [self._alert_payload(a) for a in alerts],
            'predictions': predictions.read(['prediction_type', 'prediction_text', 'probability', 'expected_delay_days', 'confidence', 'evidence_json', 'recommendation']),
        }

    @http.route('/waqf_ai/run_now', type='json', auth='user', methods=['POST'], csrf=False)
    def run_now(self, **kwargs):
        if not request.env.user.has_group('waqf_mosque_ai_risk_center.group_ai_risk_admin'):
            return {'error': 'access_denied'}
        run = request.env['waqf.ai.snapshot.run'].sudo().run_now(kwargs.get('phase_id'))
        return {'run_id': run.id, 'status': run.status, 'alerts_count': run.alerts_count}
