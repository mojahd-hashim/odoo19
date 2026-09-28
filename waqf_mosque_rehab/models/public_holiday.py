# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class MosquePublicHoliday(models.Model):
    """الإجازات الرسمية — تُستثنى من أيام الحضور اليومي المطلوبة للمهندسين."""
    _name = 'mosque.public.holiday'
    _description = 'Official Public Holiday'
    _order = 'date_from desc'

    name = fields.Char(string='الإجازة', required=True)
    date_from = fields.Date(string='من', required=True)
    date_to = fields.Date(string='إلى', required=True)
    note = fields.Char(string='ملاحظة')

    @api.constrains('date_from', 'date_to')
    def _check_dates(self):
        for rec in self:
            if rec.date_to < rec.date_from:
                raise ValidationError(_('تاريخ نهاية الإجازة قبل بدايتها.'))

    @api.model
    def _holiday_dates(self, start, end):
        days = set()
        for h in self.search([('date_from', '<=', end), ('date_to', '>=', start)]):
            d = max(h.date_from, start)
            while d <= min(h.date_to, end):
                days.add(d)
                d += timedelta(days=1)
        return days
