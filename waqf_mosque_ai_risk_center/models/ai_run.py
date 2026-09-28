# -*- coding: utf-8 -*-
import json
import logging
import time
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class WaqfAiSnapshotRun(models.Model):
    _name = 'waqf.ai.snapshot.run'
    _description = 'AI Risk Snapshot Run'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'run_datetime desc, id desc'

    name = fields.Char(default=lambda self: _('AI Risk Run'), required=True, tracking=True)
    phase_id = fields.Many2one('mosque.package', string='Phase / Package', index=True, tracking=True)
    phase_name = fields.Char(tracking=True)
    run_datetime = fields.Datetime(default=fields.Datetime.now, required=True, tracking=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('done_with_ai_error', 'Done with AI Error'),
        ('failed_ai', 'AI Failed'),
        ('failed', 'Failed'),
    ], default='draft', tracking=True, index=True)
    mosque_count = fields.Integer()
    alerts_count = fields.Integer(compute='_compute_counts', store=True)
    critical_count = fields.Integer(compute='_compute_counts', store=True)
    high_count = fields.Integer(compute='_compute_counts', store=True)
    medium_count = fields.Integer(compute='_compute_counts', store=True)
    low_count = fields.Integer(compute='_compute_counts', store=True)
    raw_snapshot_json = fields.Text()
    ai_response_json = fields.Text()
    error_message = fields.Text()
    duration_seconds = fields.Float()

    snapshot_ids = fields.One2many('waqf.ai.mosque.snapshot', 'run_id', string='Mosque Snapshots')
    alert_ids = fields.One2many('waqf.ai.alert', 'run_id', string='Alerts')
    prediction_ids = fields.One2many('waqf.ai.prediction', 'run_id', string='Predictions')
    insight_id = fields.One2many('waqf.ai.phase.insight', 'run_id', string='Phase Insight')

    def _compute_counts(self):
        Alert = self.env['waqf.ai.alert'].sudo()
        Snapshot = self.env['waqf.ai.mosque.snapshot'].sudo()

        for rec in self:
            if not rec.id:
                rec.mosque_count = 0
                rec.alerts_count = 0
                rec.critical_count = 0
                rec.high_count = 0
                rec.medium_count = 0
                rec.low_count = 0
                continue

            rec.mosque_count = Snapshot.search_count([
                ('run_id', '=', rec.id)
            ])

            rec.alerts_count = Alert.search_count([
                ('run_id', '=', rec.id)
            ])

            rec.critical_count = Alert.search_count([
                ('run_id', '=', rec.id),
                ('severity', '=', 'critical')
            ])

            rec.high_count = Alert.search_count([
                ('run_id', '=', rec.id),
                ('severity', '=', 'high')
            ])

            rec.medium_count = Alert.search_count([
                ('run_id', '=', rec.id),
                ('severity', '=', 'medium')
            ])

            rec.low_count = Alert.search_count([
                ('run_id', '=', rec.id),
                ('severity', '=', 'low')
            ])

    def action_run(self):
        self.ensure_one()
        return self._run_analysis(phase=self.phase_id)

    @api.model
    def cron_run_current_phase_analysis(self):
        return self._run_analysis()

    @api.model
    def run_now(self, phase_id=False):
        phase = self.env['mosque.package'].browse(int(phase_id)) if phase_id else False
        return self._run_analysis(phase=phase)

    @api.model
    def _get_param(self, key, default=False):
        return self.env['ir.config_parameter'].sudo().get_param(key, default)

    @api.model
    def _find_current_phase(self):
        Package = self.env['mosque.package'].sudo()
        today = fields.Date.context_today(self)
        phase = Package.search([
            ('planned_start', '<=', today),
            ('planned_end', '>=', today),
        ], order='planned_start desc', limit=1)
        if phase:
            return phase
        future = Package.search([('planned_start', '>=', today)], order='planned_start asc', limit=1)
        if future:
            return future
        return Package.search([], order='planned_start desc, id desc', limit=1)

    @api.model
    def _run_analysis(self, phase=False):
        start = time.time()
        phase = phase or self._find_current_phase()
        if not phase:
            raise UserError(_('No mosque phase/package found.'))

        run = self.create({
            'name': _('AI Risk Run - %s') % (getattr(phase, 'display_name', False) or phase.name or phase.id),
            'phase_id': phase.id,
            'phase_name': getattr(phase, 'display_name', False) or phase.name or str(phase.id),
            'status': 'running',
            'run_datetime': fields.Datetime.now(),
        })
        try:
            max_mosques = int(self._get_param('waqf_ai_max_mosques_per_run', 0) or 0)

            mosques = phase.mosque_ids.sudo()
            # التقدم الزمني والتأخير مخزّنة وتعتمد على تاريخ اليوم — نحدّثها قبل اللقطة
            mosques._recompute_progress()

            if max_mosques:
                mosques = mosques[:max_mosques]

            snapshots_payload = []

            for mosque in mosques:
                snapshot_vals, payload = (
                    self.env['waqf.ai.mosque.snapshot']
                    ._prepare_snapshot_values(run, phase, mosque)
                )

                self.env['waqf.ai.mosque.snapshot'].create(snapshot_vals)

                snapshots_payload.append(payload)

            run.write({
                'mosque_count': len(mosques),
                'raw_snapshot_json': {
                    'phase': self._phase_payload(phase),
                    'mosques_count': len(snapshots_payload),
                },
            })

            self.env.cr.commit()

            rule_alert_payloads = (
                self.env['waqf.ai.alert']
                ._generate_rule_alerts(run, snapshots_payload)
            )

            self.env.cr.commit()

            ai_error = False
            ai_response = None

            if run._get_param('waqf_ai_enabled', 'False') in ('True', 'true', '1'):

                try:
                    # تنبيهات القواعد بصيغة مختصرة حتى لا يكررها النموذج
                    rule_alerts = [{
                        'mosque_id': a.mosque_id.id or None, 'alert_type': a.alert_type,
                        'severity': a.severity, 'title': a.title,
                    } for a in run.alert_ids]
                    ai_response = run._call_azure_openai({
                        'phase': self._phase_payload(phase),
                        'mosques': snapshots_payload,
                        'rule_alerts': rule_alerts,
                    })

                    run.write({
                        'ai_response_json': json.dumps(ai_response, ensure_ascii=False, indent=2),
                    })

                    self.env.cr.commit()

                    run._store_ai_response(ai_response)

                    self.env.cr.commit()

                except Exception as exc:

                    self.env.cr.rollback()

                    ai_error = str(exc)

                    _logger.exception('Azure OpenAI call failed')

            run.env['waqf.ai.phase.insight']._build_phase_insight(
                run,
                snapshots_payload,
                ai_response if not ai_error else None,
            )

            self.env.cr.commit()

            run.write({
                'status': 'done_with_ai_error' if ai_error else 'done',
                'error_message': ai_error or False,
                'duration_seconds': time.time() - start,
            })

            self.env.cr.commit()

            return run

        except Exception as exc:

            self.env.cr.rollback()

            _logger.exception('AI Risk analysis failed')

            run.sudo().write({
                'status': 'failed',
                'error_message': str(exc),
                'duration_seconds': time.time() - start,
            })

            self.env.cr.commit()

            return run

    @api.model
    def _phase_payload(self, phase):
        return {
            'id': phase.id,
            'name': getattr(phase, 'display_name', False) or phase.name or str(phase.id),
            'phase': getattr(phase, 'phase', False),
            'planned_start': fields.Date.to_string(phase.planned_start) if getattr(phase, 'planned_start', False) else False,
            'planned_end': fields.Date.to_string(phase.planned_end) if getattr(phase, 'planned_end', False) else False,
        }

    def _call_azure_openai(self, snapshot):
        """يستدعي Azure OpenAI عبر العميل الموحّد ويعيد JSON."""
        self.ensure_one()
        res = self.env['waqf.ai.client'].chat_json([
            {'role': 'system', 'content': self._azure_system_prompt()},
            {'role': 'user', 'content': json.dumps(snapshot, ensure_ascii=False, default=str)},
        ], purpose='analysis', temperature=0.1)
        return res['json']

    AI_OUTPUT_SCHEMA = '''
أعد JSON فقط بهذا الشكل (بدون أي نص خارجه):
{
  "phase_summary": {"overall_summary": "نص", "phase_health": "good|watch|risk|critical",
                    "executive_insights": ["نص"], "recommendations": ["نص"]},
  "alerts": [{"mosque_id": رقم أو null, "contractor": "نص أو null",
              "alert_type": "delay|financial|approval|quality|supervision|boq|contractor|change_order|payment_execution_impact|data_conflict|silent_project|risk",
              "severity": "low|medium|high|critical", "title": "نص قصير", "summary": "نص",
              "root_cause": "نص", "impact": "نص", "recommendation": "نص",
              "confidence": 0.0-1.0, "priority_score": 0-100, "impact_score": 0-100, "probability_score": 0-100}],
  "predictions": [{"mosque_id": رقم أو null,
                   "prediction_type": "expected_delay|financial_overrun|quality_risk|supervision_gap|approval_bottleneck|phase_delay",
                   "prediction_text": "نص", "probability": 0.0-1.0, "expected_delay_days": رقم,
                   "confidence": 0.0-1.0, "recommendation": "نص"}]
}
استخدم mosque_id كما ورد في البيانات فقط.'''

    @api.model
    def _azure_system_prompt(self):
        from .res_config_settings import DEFAULT_ANALYSIS_PROMPT
        prompt = self._get_param('waqf_ai_analysis_prompt') or DEFAULT_ANALYSIS_PROMPT
        return prompt.strip() + '\n' + self.AI_OUTPUT_SCHEMA

    def _store_ai_response(self, ai_response):
        """يحفظ تنبيهات وتوقعات النموذج بعد التحقق منها وتطبيق حد الثقة."""
        self.ensure_one()
        response = ai_response or {}
        Alert = self.env['waqf.ai.alert']
        Pred = self.env['waqf.ai.prediction']
        valid_mosques = set(self.snapshot_ids.mapped('mosque_id').ids)
        alert_types = dict(Alert._fields['alert_type'].selection)
        severities = dict(Alert._fields['severity'].selection)
        pred_types = dict(Pred._fields['prediction_type'].selection)
        threshold = float(self._get_param('waqf_ai_confidence_threshold', 0.55) or 0)

        def num(v, default=0.0):
            try:
                return float(v)
            except (TypeError, ValueError):
                return default

        def mosque(v):
            try:
                v = int(v)
            except (TypeError, ValueError):
                return False
            return v if v in valid_mosques else False

        kept = []
        for item in response.get('alerts', []) or []:
            if not isinstance(item, dict):
                continue
            conf = num(item.get('confidence'))
            if conf > 1:
                conf = conf / 100.0
            if conf < threshold:
                continue
            item = dict(item,
                        mosque_id=mosque(item.get('mosque_id')),
                        alert_type=item.get('alert_type') if item.get('alert_type') in alert_types else 'risk',
                        severity=item.get('severity') if item.get('severity') in severities else 'medium',
                        confidence=conf)
            kept.append(Alert._create_or_update_alert(self, item, 'ai'))

        # تنبيهات الذكاء الاصطناعي السابقة التي لم تتكرر في هذا التحليل تُغلق
        Alert.search([
            ('phase_id', '=', self.phase_id.id),
            ('source', 'in', ['ai', 'hybrid']),
            ('status', 'in', ['new', 'acknowledged']),
            ('id', 'not in', [a.id for a in kept if a]),
        ]).write({'status': 'resolved', 'resolved_date': fields.Datetime.now()})

        for item in response.get('predictions', []) or []:
            if not isinstance(item, dict):
                continue
            conf = num(item.get('confidence'))
            if conf > 1:
                conf = conf / 100.0
            if conf < threshold:
                continue
            Pred.create({
                'run_id': self.id,
                'phase_id': self.phase_id.id,
                'mosque_id': mosque(item.get('mosque_id')),
                'prediction_type': item.get('prediction_type') if item.get('prediction_type') in pred_types else 'expected_delay',
                'prediction_text': item.get('prediction_text'),
                'probability': num(item.get('probability')),
                'expected_delay_days': int(num(item.get('expected_delay_days'))),
                'confidence': conf,
                'evidence_json': json.dumps(item.get('evidence') or {}, ensure_ascii=False, indent=2),
                'recommendation': item.get('recommendation'),
            })
