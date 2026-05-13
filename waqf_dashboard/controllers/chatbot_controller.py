import json
import urllib.request
import urllib.error
from odoo import http
from odoo.http import request


class WaqfChatbotController(http.Controller):

    @http.route('/dashboard/api/chat', type='json', auth='user', methods=['POST'])
    def chat(self, message='', mosque_context=None, history=None, **kw):
        """
        Proxy to Azure OpenAI.
        mosque_context: dict with current mosque data for context injection.
        history: list of {role, content} for conversation memory.
        """
        ICP = request.env['ir.config_parameter'].sudo()
        endpoint   = ICP.get_param('waqf.dashboard.azure_endpoint', '').rstrip('/')
        api_key    = ICP.get_param('waqf.dashboard.azure_key', '')
        deployment = ICP.get_param('waqf.dashboard.azure_deployment', 'gpt-4o')
        sys_prompt = ICP.get_param('waqf.dashboard.chatbot_prompt',
                                   'أنت مساعد ذكي لمتابعة مشاريع الوقف.')

        if not endpoint or not api_key:
            return {
                'reply': 'لم يتم تكوين خدمة الذكاء الاصطناعي بعد. '
                         'يرجى إضافة بيانات Azure OpenAI في إعدادات الداش بورد.',
                'error': True,
            }

        # Build context from mosque data
        context_str = ''
        if mosque_context:
            context_str = '\n\nبيانات المسجد الحالي:\n'
            m = mosque_context
            context_str += f"- الاسم: {m.get('name', '')}\n"
            context_str += f"- KPI الكلي: {m.get('overall_kpi', 0)}%\n"
            context_str += f"- الإنجاز المالي: {m.get('financial_pct', 0)}%\n"
            context_str += f"- الالتزام الزمني: {m.get('time_pct', 0)}%\n"
            context_str += f"- أيام التأخير: {m.get('days_delay', 0)}\n"
            if m.get('pending_certs'):
                context_str += f"- مستخلصات معلقة: {m.get('pending_certs')}\n"

        # Build messages
        messages = [
            {'role': 'system', 'content': sys_prompt + context_str}
        ]

        # Add history (last 6 turns)
        if history and isinstance(history, list):
            messages.extend(history[-6:])

        messages.append({'role': 'user', 'content': message})

        # Call Azure OpenAI
        url = f"{endpoint}/openai/deployments/{deployment}/chat/completions?api-version=2024-02-01"

        payload = json.dumps({
            'messages':   messages,
            'max_tokens': 800,
            'temperature': 0.4,
        }).encode('utf-8')

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                'Content-Type': 'application/json',
                'api-key':      api_key,
            },
            method='POST',
        )

        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data  = json.loads(resp.read().decode('utf-8'))
                reply = data['choices'][0]['message']['content']
                return {'reply': reply, 'error': False}
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8')
            return {'reply': f'خطأ في الاتصال بالذكاء الاصطناعي: {e.code}', 'error': True}
        except Exception as e:
            return {'reply': f'تعذر الاتصال: {str(e)}', 'error': True}