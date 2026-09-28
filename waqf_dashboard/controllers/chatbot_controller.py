import json

from odoo import http
from odoo.exceptions import UserError
from odoo.http import request

from .helpers import mosque_domain, mosque_perf, onsite_list, riyadh_today


class WaqfChatbotController(http.Controller):

    def _portfolio_context(self):
        """ملخص حي للمحفظة يُرفق بسؤال المستخدم."""
        env = request.env
        today = riyadh_today()
        rows = []
        for m in env['mosque.mosque'].sudo().search(mosque_domain(env)):
            p = mosque_perf(m, today)
            rows.append((m, p))
        by = lambda st: sum(1 for _m, p in rows if p['status'] == st)
        avg_progress = round(sum(p['actual_pct'] for _m, p in rows) / len(rows), 1) if rows else 0
        avg_planned = round(sum(p['planned_pct'] for _m, p in rows) / len(rows), 1) if rows else 0
        worst = sorted([r for r in rows if r[1]['status'] == 'critical'], key=lambda r: r[1]['variance'])[:5]
        lines = [
            f'التاريخ (الرياض): {today}',
            f'عدد المساجد: {len(rows)} · في الموعد {by("ok")} · تأخر بسيط {by("warning")} · '
            f'حرج {by("critical")} · مكتمل {by("done")} · لم يبدأ {by("not_started")}',
            f'متوسط الإنجاز (بعدد المهام المعتمدة وأوامر العمل المقبولة): {avg_progress}% '
            f'مقابل مخطط زمني {avg_planned}% — الكميات للمعلومية فقط',
            f'مستشارون في المواقع الآن: {len(onsite_list(env))}',
        ]
        if worst:
            lines.append('أكثر المساجد تأخراً: ' + '، '.join(
                f"{m.name} ({m.code}) فعلي {p['actual_pct']}% مقابل مخطط {p['planned_pct']}%"
                for m, p in worst))
        return '\n'.join(lines)

    @http.route('/dashboard/api/chat', type='json', auth='user', methods=['POST'])
    def chat(self, message='', mosque_context=None, history=None, **kw):
        env = request.env
        ICP = env['ir.config_parameter'].sudo()
        if 'waqf.ai.client' not in env:
            return {'reply': 'مركز المخاطر الذكي غير مثبت — لا يوجد ربط مع Azure OpenAI.', 'error': True}
        if ICP.get_param('waqf_ai_chat_enabled', 'True') in ('False', 'false', '0'):
            return {'reply': 'المساعد «مساند» معطّل من الإعدادات.', 'error': True}

        client = env['waqf.ai.client']
        if not client._is_configured():
            return {'reply': 'لم يتم ربط Azure OpenAI بعد. يرجى إكمال الإعدادات: '
                             'مركز المخاطر الذكي ← الإعدادات ← ربط Azure OpenAI.', 'error': True}

        prompt = (ICP.get_param('waqf_ai_chat_prompt') or ICP.get_param('waqf.dashboard.chatbot_prompt')
                  or 'أنت «مساند»، مساعد ذكي لمتابعة مشروع تأهيل المساجد. تجيب بالعربية بدقة واختصار.')
        context = '\n\nبيانات المشروع الحالية:\n' + self._portfolio_context()
        if mosque_context:
            m = mosque_context
            context += ('\n\nالمسجد المفتوح حالياً في اللوحة:\n'
                        f"- الاسم: {m.get('name', '')}\n"
                        f"- مؤشر الأداء العام: {m.get('overall_kpi', 0)}%\n"
                        f"- الإنجاز الفعلي: {m.get('financial_pct', 0)}%\n"
                        f"- المخطط حتى اليوم: {m.get('time_pct', 0)}%\n"
                        f"- أيام التأخير: {m.get('days_delay', 0)}")

        messages = [{'role': 'system', 'content': prompt + context}]
        if isinstance(history, list):
            messages += [h for h in history[-6:]
                         if isinstance(h, dict) and h.get('role') in ('user', 'assistant') and h.get('content')]
        messages.append({'role': 'user', 'content': (message or '')[:2000]})

        try:
            res = client.chat(messages, purpose='chatbot', max_tokens=900, temperature=0.4)
        except UserError as exc:
            return {'reply': 'تعذر الحصول على رد من Azure OpenAI.\n' + str(exc).split('\n')[0], 'error': True}
        return {'reply': res['content'], 'error': False}
