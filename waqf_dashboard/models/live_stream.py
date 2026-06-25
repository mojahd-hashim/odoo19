from odoo import models, fields, api, _
from datetime import datetime


class WaqfLiveStream(models.Model):
    """Track active live streams for dashboard notification."""
    _name = 'waqf.live.stream'
    _description = 'Live Stream Session'
    _order = 'start_time desc'

    name        = fields.Char(string='Stream Title', required=True)
    mosque_id   = fields.Many2one('mosque.mosque', string='Mosque')
    stream_url  = fields.Char(string='Stream URL', required=True)
    stream_live_url  = fields.Char(string='Stream URL')
    started_by  = fields.Many2one('hr.employee', string='Started By')
    start_time  = fields.Datetime(string='Start Time', default=fields.Datetime.now)
    end_time    = fields.Datetime(string='End Time')
    is_active   = fields.Boolean(string='Active', default=True)
    viewers     = fields.Integer(string='Viewer Count', default=0)

    def action_end_stream(self):
        self.write({'is_active': False, 'end_time': datetime.now()})
        # Clear global setting
        self.env['ir.config_parameter'].sudo().set_param(
            'waqf.dashboard.live_stream_url', '')

    @api.model
    def get_active_stream(self):
        stream = self.search([('is_active', '=', True)], limit=1, order='start_time desc')
        if not stream:
            return None
        return {
            'id':         stream.id,
            'name':       stream.name,
            'mosque':     stream.mosque_id.name if stream.mosque_id else '',
            'url':        stream.stream_url,
            'start_time': str(stream.start_time),
            'started_by': stream.started_by.name if stream.started_by else '',
        }