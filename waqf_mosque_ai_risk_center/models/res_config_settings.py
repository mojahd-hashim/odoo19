# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from odoo.exceptions import UserError

from .ai_client import DEFAULT_API_VERSION

DEFAULT_ANALYSIS_PROMPT = '''أنت وكيل تحليل مخاطر تنفيذي لمشروع تأهيل المساجد (وقف الملك عبدالله).
حلل بيانات المرحلة الحالية فقط.
اربط بين الإنجاز الفعلي والمخطط، والمستخلصات، والاعتمادات، والحضور اليومي للمهندسين
(8 ساعات من الأحد إلى الخميس)، وأوامر التغيير، وتنفيذ جدول الكميات.
لا تنشئ تنبيهًا إلا إذا كان له دليل واضح من الأرقام، ولا تكرر تنبيهات القواعد.
لا تصف الأرقام فقط، بل اربط السبب بالأثر وحدد الأولوية والإجراء المطلوب.
اكتب بالعربية الإدارية المختصرة.'''

DEFAULT_CHAT_PROMPT = ('أنت «مساند»، مساعد ذكي لمتابعة مشروع تأهيل المساجد في وقف الملك عبدالله. '
                       'تجيب بالعربية بدقة واختصار، وتعتمد على البيانات المرفقة ولا تخترع أرقاماً.')


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Azure OpenAI connection ─────────────────────────────────
    waqf_ai_azure_endpoint = fields.Char(
        string='رابط Azure OpenAI', config_parameter='waqf_ai_azure_endpoint')
    waqf_ai_azure_api_key = fields.Char(
        string='مفتاح API', config_parameter='waqf_ai_azure_api_key')
    waqf_ai_azure_deployment = fields.Char(
        string='اسم الـ Deployment', config_parameter='waqf_ai_azure_deployment')
    waqf_ai_azure_api_version = fields.Char(
        string='إصدار API', config_parameter='waqf_ai_azure_api_version',
        default=DEFAULT_API_VERSION)
    waqf_ai_reasoning_model = fields.Boolean(
        string='نموذج استدلالي (o-series / GPT-5)', config_parameter='waqf_ai_reasoning_model')
    waqf_ai_temperature = fields.Float(
        string='درجة الإبداع (temperature)', config_parameter='waqf_ai_temperature', default=0.2)
    waqf_ai_max_tokens = fields.Integer(
        string='الحد الأقصى للمخرجات (tokens)', config_parameter='waqf_ai_max_tokens', default=2500)
    waqf_ai_timeout = fields.Integer(
        string='مهلة الاتصال (ثانية)', config_parameter='waqf_ai_timeout', default=90)

    # ── Features ───────────────────────────────────────────────
    waqf_ai_enabled = fields.Boolean(
        string='استخدام الذكاء الاصطناعي في تحليل المخاطر', config_parameter='waqf_ai_enabled')
    waqf_ai_chat_enabled = fields.Boolean(
        string='تفعيل المساعد «مساند» في لوحة الإدارة', config_parameter='waqf_ai_chat_enabled',
        default=True)
    waqf_ai_analysis_prompt = fields.Text(string='تعليمات تحليل المخاطر')
    waqf_ai_chat_prompt = fields.Text(string='تعليمات المساعد «مساند»')

    # ── Run settings ───────────────────────────────────────────
    waqf_ai_run_interval_hours = fields.Integer(
        string='التحليل كل (ساعة)', default=2, config_parameter='waqf_ai_run_interval_hours')
    waqf_ai_max_mosques_per_run = fields.Integer(
        string='أقصى عدد مساجد في التحليل', default=0, config_parameter='waqf_ai_max_mosques_per_run')
    waqf_ai_confidence_threshold = fields.Float(
        string='أدنى ثقة لقبول تنبيه الذكاء الاصطناعي', default=0.55,
        config_parameter='waqf_ai_confidence_threshold')

    # ── Status (read-only) ─────────────────────────────────────
    waqf_ai_calls_30d = fields.Integer(string='اتصالات آخر 30 يوم', compute='_compute_ai_usage')
    waqf_ai_tokens_30d = fields.Integer(string='Tokens آخر 30 يوم', compute='_compute_ai_usage')
    waqf_ai_errors_30d = fields.Integer(string='أخطاء آخر 30 يوم', compute='_compute_ai_usage')

    def _compute_ai_usage(self):
        Log = self.env['waqf.ai.call.log'].sudo()
        since = fields.Datetime.subtract(fields.Datetime.now(), days=30)
        logs = Log.search([('create_date', '>=', since)])
        for rec in self:
            rec.waqf_ai_calls_30d = len(logs)
            rec.waqf_ai_tokens_30d = sum(logs.mapped('total_tokens'))
            rec.waqf_ai_errors_30d = len(logs.filtered(lambda l: l.status == 'error'))

    # Text fields cannot use config_parameter — stored manually
    @api.model
    def get_values(self):
        res = super().get_values()
        ICP = self.env['ir.config_parameter'].sudo()
        res.update(
            waqf_ai_analysis_prompt=ICP.get_param('waqf_ai_analysis_prompt') or DEFAULT_ANALYSIS_PROMPT,
            waqf_ai_chat_prompt=(ICP.get_param('waqf_ai_chat_prompt')
                                 or ICP.get_param('waqf.dashboard.chatbot_prompt') or DEFAULT_CHAT_PROMPT),
        )
        return res

    def set_values(self):
        super().set_values()
        ICP = self.env['ir.config_parameter'].sudo()
        ICP.set_param('waqf_ai_analysis_prompt', self.waqf_ai_analysis_prompt or '')
        ICP.set_param('waqf_ai_chat_prompt', self.waqf_ai_chat_prompt or '')
        # الفاصل الزمني للتحليل يُطبَّق على المهمة المجدولة
        cron = self.env.ref('waqf_mosque_ai_risk_center.ir_cron_waqf_ai_risk_analysis', raise_if_not_found=False)
        hours = max(1, self.waqf_ai_run_interval_hours or 2)
        if cron and cron.sudo().interval_number != hours:
            cron.sudo().write({'interval_number': hours, 'interval_type': 'hours'})

    # ── Buttons ────────────────────────────────────────────────
    def _form_ai_config(self):
        self.ensure_one()
        Client = self.env['waqf.ai.client']
        cfg = Client._get_config()
        cfg.update({
            'endpoint': (self.waqf_ai_azure_endpoint or '').strip().rstrip('/'),
            'api_key': (self.waqf_ai_azure_api_key or '').strip(),
            'deployment': (self.waqf_ai_azure_deployment or '').strip(),
            'api_version': (self.waqf_ai_azure_api_version or DEFAULT_API_VERSION).strip(),
            'reasoning': self.waqf_ai_reasoning_model,
            'temperature': self.waqf_ai_temperature,
            'timeout': self.waqf_ai_timeout or 90,
        })
        return cfg

    def action_waqf_ai_test_connection(self):
        """اختبار الاتصال بالقيم الحالية في النموذج (قبل الحفظ)."""
        cfg = self._form_ai_config()
        try:
            res = self.env['waqf.ai.client'].chat(
                [{'role': 'system', 'content': 'Reply with one short Arabic sentence.'},
                 {'role': 'user', 'content': 'اكتب: تم الاتصال بنجاح'}],
                purpose='test', max_tokens=60, cfg=cfg)
        except UserError as exc:
            return self._ai_notify(_('فشل الاتصال بـ Azure OpenAI'), str(exc), 'danger', sticky=True)
        usage = res.get('usage') or {}
        msg = _('النموذج: %(model)s · زمن الاستجابة: %(ms)s ms · Tokens: %(tok)s\nالرد: %(reply)s') % {
            'model': res.get('model'), 'ms': res.get('latency_ms'),
            'tok': usage.get('total_tokens', 0), 'reply': (res.get('content') or '')[:120],
        }
        return self._ai_notify(_('تم الاتصال بـ Azure OpenAI بنجاح'), msg, 'success')

    def action_waqf_ai_run_now(self):
        self.execute()
        run = self.env['waqf.ai.snapshot.run'].sudo().run_now()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'waqf.ai.snapshot.run',
            'res_id': run.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_waqf_ai_open_logs(self):
        return self.env['ir.actions.act_window']._for_xml_id(
            'waqf_mosque_ai_risk_center.action_ai_call_log')

    @api.model
    def _ai_notify(self, title, message, kind, sticky=False):
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {'title': title, 'message': message, 'type': kind, 'sticky': sticky},
        }
