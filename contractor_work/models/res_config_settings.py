# -*- coding: utf-8 -*-
from odoo import models, fields, api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ABCD Grade payment percentages
    contractor_grade_a_pct = fields.Float(
        string='نسبة دفع التقييم A %',
        default=100, config_parameter='contractor.grade_a_pct')
    contractor_grade_b_pct = fields.Float(
        string='نسبة دفع التقييم B %',
        default=100, config_parameter='contractor.grade_b_pct')
    contractor_grade_c_pct = fields.Float(
        string='نسبة دفع التقييم C %',
        default=0, config_parameter='contractor.grade_c_pct')
    contractor_grade_d_pct = fields.Float(
        string='نسبة دفع التقييم D %',
        default=0, config_parameter='contractor.grade_d_pct')

    # Warranty alert
    contractor_warranty_alert_days = fields.Integer(
        string='التنبيه قبل انتهاء الضمان (يوم)',
        default=30, config_parameter='contractor.warranty_alert_days')
