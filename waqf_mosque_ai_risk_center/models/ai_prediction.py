# -*- coding: utf-8 -*-
from odoo import api, fields, models


class WaqfAiPrediction(models.Model):
    _name = 'waqf.ai.prediction'
    _description = 'AI Risk Prediction'
    _order = 'create_date desc'

    run_id = fields.Many2one('waqf.ai.snapshot.run', ondelete='cascade', index=True)
    phase_id = fields.Many2one('mosque.package', index=True)
    mosque_id = fields.Many2one('mosque.mosque', index=True)
    prediction_type = fields.Selection([
        ('expected_delay', 'Expected Delay'), ('financial_overrun', 'Financial Overrun'),
        ('quality_risk', 'Quality Risk'), ('supervision_gap', 'Supervision Gap'),
        ('approval_bottleneck', 'Approval Bottleneck'), ('phase_delay', 'Phase Delay'),
    ], required=True, index=True)
    prediction_text = fields.Text()
    probability = fields.Float()
    expected_delay_days = fields.Integer()
    confidence = fields.Float()
    evidence_json = fields.Json()
    recommendation = fields.Text()

    @api.model
    def create_from_ai(self, run, item):
        return self.create({
            'run_id': run.id,
            'phase_id': run.phase_id.id,
            'mosque_id': item.get('mosque_id') or False,
            'prediction_type': item.get('prediction_type') or 'expected_delay',
            'prediction_text': item.get('prediction_text'),
            'probability': float(item.get('probability') or 0.0),
            'expected_delay_days': int(item.get('expected_delay_days') or 0),
            'confidence': float(item.get('confidence') or 0.0),
            'evidence_json': item.get('evidence') or {},
            'recommendation': item.get('recommendation'),
        })


class WaqfAiPhaseInsight(models.Model):
    _name = 'waqf.ai.phase.insight'
    _description = 'AI Phase Insight'
    _order = 'create_date desc'

    run_id = fields.Many2one('waqf.ai.snapshot.run', required=True, ondelete='cascade', index=True)
    phase_id = fields.Many2one('mosque.package', index=True)
    phase_health = fields.Selection([('good', 'Good'), ('watch', 'Watch'), ('risk', 'Risk'), ('critical', 'Critical')], default='watch')
    overall_summary = fields.Text()
    financial_risk_level = fields.Selection([('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], default='low')
    quality_risk_level = fields.Selection([('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], default='low')
    supervision_risk_level = fields.Selection([('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], default='low')
    approval_risk_level = fields.Selection([('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], default='low')
    critical_projects_count = fields.Integer()
    predicted_delays_count = fields.Integer()
    total_pending_payments = fields.Float()
    total_change_orders_value = fields.Float()
    total_delay_days = fields.Integer()
    executive_insights_json = fields.Json()
    recommendations_json = fields.Json()

    @api.model
    def _build_phase_insight(self, run, snapshots):
        critical = len(run.alert_ids.filtered(lambda a: a.severity == 'critical'))
        high = len(run.alert_ids.filtered(lambda a: a.severity == 'high'))
        health = 'good'
        if critical >= 3:
            health = 'critical'
        elif critical or high >= 3:
            health = 'risk'
        elif high:
            health = 'watch'
        vals = {
            'run_id': run.id,
            'phase_id': run.phase_id.id,
            'phase_health': health,
            'overall_summary': 'تم تحليل %s مسجد في المرحلة، ونتج عنها %s تنبيه.' % (len(snapshots), len(run.alert_ids)),
            'financial_risk_level': 'high' if any(s.get('pending_certificates_value', 0) > 0 for s in snapshots) else 'low',
            'quality_risk_level': 'high' if any(s.get('ncr_count_30d', 0) or s.get('safety_incidents_30d', 0) for s in snapshots) else 'low',
            'supervision_risk_level': 'high' if any(s.get('validated_visits_7d', 0) < 2 for s in snapshots) else 'low',
            'approval_risk_level': 'high' if any(s.get('pending_change_orders_count', 0) for s in snapshots) else 'low',
            'critical_projects_count': critical,
            'predicted_delays_count': len([s for s in snapshots if s.get('days_delay', 0) > 0]),
            'total_pending_payments': sum(s.get('pending_certificates_value', 0) for s in snapshots),
            'total_change_orders_value': sum(s.get('change_orders_value', 0) for s in snapshots),
            'total_delay_days': sum(s.get('days_delay', 0) for s in snapshots),
            'executive_insights_json': [],
            'recommendations_json': [],
        }
        return self.create(vals)
