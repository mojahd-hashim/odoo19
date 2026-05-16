# -*- coding: utf-8 -*-
import json
import logging
import time
from datetime import timedelta
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

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
    raw_snapshot_json = fields.Json()
    ai_response_json = fields.Json()
    error_message = fields.Text()
    duration_seconds = fields.Float()

    snapshot_ids = fields.One2many('waqf.ai.mosque.snapshot', 'run_id', string='Mosque Snapshots')
    alert_ids = fields.One2many('waqf.ai.alert', 'run_id', string='Alerts')
    prediction_ids = fields.One2many('waqf.ai.prediction', 'run_id', string='Predictions')
    insight_id = fields.One2many('waqf.ai.phase.insight', 'run_id', string='Phase Insight')

    @api.depends('alert_ids.severity')
    def _compute_counts(self):
        for rec in self:
            alerts = rec.alert_ids
            rec.alerts_count = len(alerts)
            rec.critical_count = len(alerts.filtered(lambda a: a.severity == 'critical'))
            rec.high_count = len(alerts.filtered(lambda a: a.severity == 'high'))
            rec.medium_count = len(alerts.filtered(lambda a: a.severity == 'medium'))
            rec.low_count = len(alerts.filtered(lambda a: a.severity == 'low'))

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
        #todo
        # phase = Package.search([
        #     ('planned_start', '<=', today),
        #     ('planned_end', '>=', today),
        # ], order='planned_start desc', limit=1)
        phase = Package.search([
            ('id', '=', 6)
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
            if max_mosques:
                mosques = mosques[:max_mosques]
            snapshots_payload = []
            for mosque in mosques:
                snapshot_vals, payload = self.env['waqf.ai.mosque.snapshot']._prepare_snapshot_values(run, phase, mosque)
                self.env['waqf.ai.mosque.snapshot'].create(snapshot_vals)
                snapshots_payload.append(payload)

            run.write({
                'mosque_count': len(mosques),
                'raw_snapshot_json': {
                    'phase': self._phase_payload(phase),
                    'mosques': snapshots_payload,
                },
            })

            rule_alert_payloads = self.env['waqf.ai.alert']._generate_rule_alerts(run, snapshots_payload)
            ai_error = False
            if run._get_param('waqf_ai_enabled', 'False') in ('True', 'true', '1'):
                try:
                    ai_response = self._call_azure_openai({
                        'phase': self._phase_payload(phase),
                        'mosques': snapshots_payload,
                        'rule_alerts': rule_alert_payloads,
                    })
                    run.ai_response_json = ai_response
                    run._store_ai_response(ai_response)
                except Exception as exc:
                    ai_error = str(exc)
                    _logger.exception('Azure OpenAI call failed')

            self.env['waqf.ai.phase.insight']._build_phase_insight(run, snapshots_payload)
            status = 'done_with_ai_error' if ai_error else 'done'
            run.write({
                'status': status,
                'error_message': ai_error or False,
                'duration_seconds': time.time() - start,
            })
            return run
        except Exception as exc:
            _logger.exception('AI Risk analysis failed')
            run.write({
                'status': 'failed',
                'error_message': str(exc),
                'duration_seconds': time.time() - start,
            })
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
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        endpoint = ICP.get_param('waqf_ai_azure_endpoint')
        api_key = ICP.get_param('waqf_ai_azure_api_key')
        deployment = ICP.get_param('waqf_ai_azure_deployment')
        if not endpoint or not api_key or not deployment:
            raise UserError(_('Azure OpenAI settings are incomplete.'))

        endpoint = endpoint.rstrip('/')
        url = '%s/openai/deployments/%s/chat/completions?api-version=2024-02-15-preview' % (endpoint, deployment)
        system_prompt = self._azure_system_prompt()
        payload = {
            'messages': [
                {'role': 'system', 'content': system_prompt},
                {'role': 'user', 'content': json.dumps(snapshot, ensure_ascii=False, default=str)},
            ],
            'temperature': 0.1,
            'response_format': {'type': 'json_object'},
        }
        data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        req = urlrequest.Request(url, data=data, headers={
            'Content-Type': 'application/json',
            'api-key': api_key,
        }, method='POST')
        try:
            with urlrequest.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read().decode('utf-8'))
        except HTTPError as exc:
            raise UserError(_('Azure OpenAI HTTP error: %s - %s') % (exc.code, exc.read().decode('utf-8', errors='ignore')))
        except URLError as exc:
            raise UserError(_('Azure OpenAI connection error: %s') % exc)
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '{}')
        return json.loads(content)

    @api.model
    def _azure_system_prompt(self):
        return '''أنت وكيل تحليل مخاطر تنفيذي لمشروع تأهيل المساجد.
حلل بيانات المرحلة الحالية فقط.
اربط بين الأرقام والتقارير والدفعات والاعتمادات والزيارات وأوامر التغيير وتنفيذ BOQ.
استخرج التنبيهات والمخاطر والتوقعات التي تساعد الإدارة على اتخاذ القرار.
لا تنشئ تنبيهًا إلا إذا كان له دليل واضح.
لا تكرر التنبيهات.
لا تصف الأرقام فقط، بل اربط السبب بالأثر.
حدد الأولوية التنفيذية.
اكتب بالعربية الإدارية المختصرة.
أعد JSON فقط بالشكل المطلوب: phase_summary, alerts, predictions.'''

    def _store_ai_response(self, ai_response):
        self.ensure_one()
        run = self
        confidence_threshold = float(self._get_param('waqf_ai_confidence_threshold', 0.55) or 0.55)
        for item in response.get('alerts', []) or []:
            if float(item.get('confidence') or 0.0) >= confidence_threshold:
                self.env['waqf.ai.alert']._create_or_update_alert(run, item, source='ai')
        for item in response.get('predictions', []) or []:
            self.env['waqf.ai.prediction'].create_from_ai(run, item)
