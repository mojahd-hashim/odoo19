# -*- coding: utf-8 -*-
"""Shared Azure OpenAI client — used by the risk analysis and the dashboard chatbot.

Supports both Azure endpoint styles:
  • classic : {endpoint}/openai/deployments/{deployment}/chat/completions?api-version=YYYY-MM-DD
  • v1      : {endpoint}/openai/v1/chat/completions   (api version = "v1", deployment sent as "model")
"""
import json
import logging
import time
from urllib import request as urlrequest
from urllib.error import HTTPError, URLError

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

P = 'waqf_ai_'                      # ir.config_parameter prefix
DEFAULT_API_VERSION = '2024-10-21'
RETRY_CODES = (429, 500, 502, 503, 504)

HTTP_HINTS = {
    400: 'الطلب مرفوض — قد تكون المعاملات غير مدعومة لهذا النموذج (جرّب تفعيل «نموذج استدلالي») أو حجبه فلتر المحتوى.',
    401: 'مفتاح API غير صحيح أو منتهي.',
    403: 'لا توجد صلاحية — تحقق من إعدادات الشبكة/الجدار الناري في Azure.',
    404: 'الرابط أو اسم الـ Deployment أو إصدار API غير صحيح.',
    429: 'تم تجاوز الحصة أو معدل الطلبات في Azure — حاول لاحقاً أو ارفع الحصة.',
}


class WaqfAiClient(models.AbstractModel):
    _name = 'waqf.ai.client'
    _description = 'Azure OpenAI Client'

    # ── Configuration ──────────────────────────────────────────
    @api.model
    def _get_config(self):
        ICP = self.env['ir.config_parameter'].sudo()
        get = ICP.get_param
        cfg = {
            'endpoint': (get(P + 'azure_endpoint') or get('waqf.dashboard.azure_endpoint') or '').strip().rstrip('/'),
            'api_key': (get(P + 'azure_api_key') or get('waqf.dashboard.azure_key') or '').strip(),
            'deployment': (get(P + 'azure_deployment') or get('waqf.dashboard.azure_deployment') or '').strip(),
            'api_version': (get(P + 'azure_api_version') or DEFAULT_API_VERSION).strip(),
            'reasoning': get(P + 'reasoning_model') in ('True', 'true', '1'),
            'temperature': float(get(P + 'temperature') or 0.2),
            'max_tokens': int(get(P + 'max_tokens') or 2500),
            'timeout': int(get(P + 'timeout') or 90),
        }
        return cfg

    @api.model
    def _is_configured(self, cfg=None):
        cfg = cfg or self._get_config()
        return bool(cfg['endpoint'] and cfg['api_key'] and cfg['deployment'])

    @api.model
    def _build_url(self, cfg):
        ep = cfg['endpoint']
        # يقبل الرابط الأساسي أو رابطاً كاملاً منسوخاً من Azure
        for cut in ('/openai/', '/openai'):
            if cut in ep:
                ep = ep.split(cut)[0]
        if cfg['api_version'].lower() in ('v1', 'latest', 'preview'):
            return '%s/openai/v1/chat/completions' % ep, True
        return '%s/openai/deployments/%s/chat/completions?api-version=%s' % (
            ep, cfg['deployment'], cfg['api_version']), False

    # ── Call ────────────────────────────────────────────────────
    @api.model
    def chat(self, messages, purpose='analysis', json_mode=False,
             max_tokens=None, temperature=None, cfg=None):
        """Send a chat completion. Returns dict(content, usage, latency_ms, model).
        Raises UserError with an Arabic explanation on failure."""
        cfg = cfg or self._get_config()
        if not self._is_configured(cfg):
            raise UserError(_('إعدادات Azure OpenAI غير مكتملة (الرابط، المفتاح، اسم الـ Deployment).'))

        url, is_v1 = self._build_url(cfg)
        body = {'messages': messages}
        if is_v1:
            body['model'] = cfg['deployment']
        limit = int(max_tokens or cfg['max_tokens'])
        if cfg['reasoning']:
            # نماذج o-series / GPT-5: لا تدعم temperature وتستخدم max_completion_tokens
            body['max_completion_tokens'] = limit
        else:
            body['max_tokens'] = limit
            body['temperature'] = cfg['temperature'] if temperature is None else temperature
        if json_mode:
            body['response_format'] = {'type': 'json_object'}

        data = json.dumps(body, ensure_ascii=False).encode('utf-8')
        headers = {'Content-Type': 'application/json', 'api-key': cfg['api_key']}

        start = time.time()
        attempt, error, result = 0, None, None
        while attempt < 3:
            attempt += 1
            try:
                req = urlrequest.Request(url, data=data, headers=headers, method='POST')
                with urlrequest.urlopen(req, timeout=cfg['timeout']) as resp:
                    result = json.loads(resp.read().decode('utf-8'))
                error = None
                break
            except HTTPError as exc:
                detail = exc.read().decode('utf-8', errors='ignore')[:600]
                error = 'HTTP %s — %s\n%s' % (exc.code, HTTP_HINTS.get(exc.code, ''), detail)
                if exc.code in RETRY_CODES and attempt < 3:
                    wait = min(10, int(exc.headers.get('Retry-After') or 2 * attempt))
                    time.sleep(wait)
                    continue
                break
            except (URLError, TimeoutError, OSError) as exc:
                error = _('تعذر الاتصال بـ Azure: %s') % exc
                if attempt < 3:
                    time.sleep(2 * attempt)
                    continue
                break

        latency = int((time.time() - start) * 1000)
        usage = (result or {}).get('usage') or {}
        self._log_call(purpose, cfg, 'error' if error else 'ok', latency, usage, error)
        if error:
            raise UserError(error)

        try:
            content = result['choices'][0]['message'].get('content') or ''
        except (KeyError, IndexError, TypeError):
            raise UserError(_('استجابة غير متوقعة من Azure: %s') % json.dumps(result)[:400])
        return {
            'content': content,
            'usage': usage,
            'latency_ms': latency,
            'model': result.get('model') or cfg['deployment'],
        }

    @api.model
    def chat_json(self, messages, purpose='analysis', **kw):
        res = self.chat(messages, purpose=purpose, json_mode=True, **kw)
        text = (res['content'] or '').strip()
        if text.startswith('```'):
            text = text.strip('`')
            text = text[text.find('{'):]
        try:
            res['json'] = json.loads(text or '{}')
        except ValueError:
            raise UserError(_('النموذج لم يُعد JSON صالحاً: %s') % text[:300])
        return res

    # ── Usage log (own cursor: survives rollbacks of the caller) ─
    @api.model
    def _log_call(self, purpose, cfg, status, latency, usage, error):
        try:
            with self.env.registry.cursor() as cr:
                env = api.Environment(cr, self.env.uid, self.env.context)
                env['waqf.ai.call.log'].sudo().create({
                    'purpose': purpose,
                    'deployment': cfg.get('deployment'),
                    'status': status,
                    'latency_ms': latency,
                    'prompt_tokens': int(usage.get('prompt_tokens') or 0),
                    'completion_tokens': int(usage.get('completion_tokens') or 0),
                    'total_tokens': int(usage.get('total_tokens') or 0),
                    'error': (error or '')[:2000] or False,
                    'user_id': self.env.uid,
                })
        except Exception:
            _logger.exception('Could not write AI call log')


class WaqfAiCallLog(models.Model):
    _name = 'waqf.ai.call.log'
    _description = 'Azure OpenAI Call Log'
    _order = 'create_date desc, id desc'
    _rec_name = 'purpose'

    purpose = fields.Selection([
        ('analysis', 'تحليل المخاطر'),
        ('chatbot', 'المساعد مساند'),
        ('test', 'اختبار الاتصال'),
    ], string='الاستخدام', required=True, index=True)
    deployment = fields.Char(string='Deployment')
    status = fields.Selection([('ok', 'ناجح'), ('error', 'خطأ')], string='النتيجة', index=True)
    latency_ms = fields.Integer(string='زمن الاستجابة (ms)')
    prompt_tokens = fields.Integer(string='Tokens الإدخال')
    completion_tokens = fields.Integer(string='Tokens المخرجات')
    total_tokens = fields.Integer(string='إجمالي Tokens')
    error = fields.Text(string='الخطأ')
    user_id = fields.Many2one('res.users', string='المستخدم')

    @api.autovacuum
    def _gc_old_logs(self):
        """حذف السجلات الأقدم من 90 يوماً."""
        limit = fields.Datetime.subtract(fields.Datetime.now(), days=90)
        self.search([('create_date', '<', limit)]).unlink()
