from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── AI Chatbot ────────────────────────────────────────────
    waqf_azure_openai_endpoint = fields.Char(
        string='Azure OpenAI Endpoint',
        config_parameter='waqf.dashboard.azure_endpoint',
        help='e.g. https://your-resource.openai.azure.com',
    )
    waqf_azure_openai_key = fields.Char(
        string='Azure OpenAI API Key',
        config_parameter='waqf.dashboard.azure_key',
    )
    waqf_azure_deployment = fields.Char(
        string='Azure Deployment Name',
        config_parameter='waqf.dashboard.azure_deployment',
        default='gpt-4o',
    )
    waqf_chatbot_system_prompt = fields.char(
        string='Chatbot System Prompt',
        config_parameter='waqf.dashboard.chatbot_prompt',
        default='أنت مساعد ذكي متخصص في متابعة مشروع تأهيل المساجد لكوقف. '
                'تجيب بالعربية بشكل دقيق ومختصر.',
    )

    # ── Live Stream ───────────────────────────────────────────
    waqf_live_stream_enabled = fields.Boolean(
        string='Enable Live Stream Feature',
        config_parameter='waqf.dashboard.live_stream_enabled',
        default=True,
    )
    waqf_live_stream_url = fields.Char(
        string='Active Live Stream URL',
        config_parameter='waqf.dashboard.live_stream_url',
        help='YouTube/custom RTMP embed URL — set when stream is live',
    )
    waqf_live_stream_label = fields.Char(
        string='Live Stream Label',
        config_parameter='waqf.dashboard.live_stream_label',
        default='بث مباشر من الموقع',
    )

    # ── Dashboard ─────────────────────────────────────────────
    waqf_dashboard_refresh_interval = fields.Integer(
        string='Auto-refresh Interval (seconds)',
        config_parameter='waqf.dashboard.refresh_interval',
        default=60,
    )
    waqf_dashboard_show_financial = fields.Boolean(
        string='Show Financial Data',
        config_parameter='waqf.dashboard.show_financial',
        default=True,
    )

    @api.model
    def get_dashboard_config(self):
        """Return config dict for dashboard JS."""
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'azure_endpoint':   ICP.get_param('waqf.dashboard.azure_endpoint', ''),
            'azure_key':        ICP.get_param('waqf.dashboard.azure_key', ''),
            'azure_deployment': ICP.get_param('waqf.dashboard.azure_deployment', 'gpt-4o'),
            'chatbot_prompt':   ICP.get_param('waqf.dashboard.chatbot_prompt', ''),
            'live_stream_enabled': ICP.get_param(
                'waqf.dashboard.live_stream_enabled', 'True') == 'True',
            'live_stream_url':   ICP.get_param('waqf.dashboard.live_stream_url', ''),
            'live_stream_label': ICP.get_param('waqf.dashboard.live_stream_label', 'بث مباشر'),
            'refresh_interval':  int(ICP.get_param(
                'waqf.dashboard.refresh_interval', 60)),
        }