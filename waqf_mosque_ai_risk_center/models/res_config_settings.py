# -*- coding: utf-8 -*-
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    waqf_ai_azure_endpoint = fields.Char(config_parameter='waqf_ai_azure_endpoint')
    waqf_ai_azure_api_key = fields.Char(config_parameter='waqf_ai_azure_api_key')
    waqf_ai_azure_deployment = fields.Char(config_parameter='waqf_ai_azure_deployment')
    waqf_ai_enabled = fields.Boolean(config_parameter='waqf_ai_enabled')
    waqf_ai_run_interval_hours = fields.Integer(default=2, config_parameter='waqf_ai_run_interval_hours')
    waqf_ai_max_mosques_per_run = fields.Integer(default=0, config_parameter='waqf_ai_max_mosques_per_run')
    waqf_ai_confidence_threshold = fields.Float(default=0.55, config_parameter='waqf_ai_confidence_threshold')
