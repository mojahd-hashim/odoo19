from odoo import models, fields, api, _


class WaqfMobileSettings(models.TransientModel):
    """
    App-wide settings for the Flutter mobile app.
    Stored as ir.config_parameter for persistence.
    Accessible via GET /api/waqf/settings
    """
    _name = 'res.config.settings'
    _inherit = 'res.config.settings'

    # ── Geofence ──────────────────────────────────────────────────
    waqf_default_geofence_radius = fields.Integer(
        string='Default Geofence Radius (m)',
        default=100,
        config_parameter='waqf.mobile.geofence_radius',
        help='Default radius in meters for mosque geofence. '
             'Can be overridden per mosque.',
    )
    waqf_min_visit_minutes = fields.Integer(
        string='Minimum Visit Duration (minutes)',
        default=30,
        config_parameter='waqf.mobile.min_visit_minutes',
        help='Visits shorter than this are flagged as incomplete.',
    )
    waqf_long_stay_hours = fields.Integer(
        string='Long Stay Alert (hours)',
        default=8,
        config_parameter='waqf.mobile.long_stay_hours',
        help='Alert supervisor if still checked-in after this many hours.',
    )

    # ── Check-in mode ─────────────────────────────────────────────
    waqf_auto_checkin = fields.Boolean(
        string='Auto Check-in (Silent)',
        default=False,
        config_parameter='waqf.mobile.auto_checkin',
        help='If enabled, check-in happens silently without notification prompt.',
    )
    waqf_require_qr = fields.Boolean(
        string='Require QR Scan for Check-in',
        default=False,
        config_parameter='waqf.mobile.require_qr',
        help='If enabled, GPS alone is not enough — QR scan also required.',
    )

    # ── Supervision report ────────────────────────────────────────
    waqf_report_required_on_checkout = fields.Boolean(
        string='Require Report on Checkout',
        default=False,
        config_parameter='waqf.mobile.report_required',
        help='If enabled, supervisor must submit a report before checkout.',
    )
    waqf_report_min_photos = fields.Integer(
        string='Minimum Photos per Report',
        default=1,
        config_parameter='waqf.mobile.min_photos',
    )

    # ── Notifications ─────────────────────────────────────────────
    waqf_notify_pending_worklogs = fields.Boolean(
        string='Notify on Pending Work Logs',
        default=True,
        config_parameter='waqf.mobile.notify_pending',
        help='Send push notification when contractor submits work for approval.',
    )
    waqf_notify_no_visit_days = fields.Integer(
        string='Alert After N Days Without Visit',
        default=2,
        config_parameter='waqf.mobile.no_visit_alert_days',
    )

    # ── App config ────────────────────────────────────────────────
    waqf_app_version_min = fields.Char(
        string='Minimum App Version',
        default='1.0.0',
        config_parameter='waqf.mobile.min_version',
        help='Force update if app version is below this.',
    )
    waqf_maintenance_mode = fields.Boolean(
        string='Maintenance Mode',
        default=False,
        config_parameter='waqf.mobile.maintenance',
        help='If enabled, app shows maintenance screen.',
    )
    waqf_maintenance_message = fields.Char(
        string='Maintenance Message',
        default='النظام في وضع الصيانة — يرجى المحاولة لاحقاً',
        config_parameter='waqf.mobile.maintenance_msg',
    )

    @api.model
    def get_mobile_config(self):
        """
        Returns all app settings as a dict.
        Called by GET /api/waqf/settings
        """
        ICP = self.env['ir.config_parameter'].sudo()
        return {
            'geofence': {
                'default_radius_m':   int(ICP.get_param('waqf.mobile.geofence_radius', 100)),
                'min_visit_minutes':  int(ICP.get_param('waqf.mobile.min_visit_minutes', 30)),
                'long_stay_hours':    int(ICP.get_param('waqf.mobile.long_stay_hours', 8)),
                'auto_checkin':       ICP.get_param('waqf.mobile.auto_checkin', 'False') == 'True',
                'require_qr':         ICP.get_param('waqf.mobile.require_qr', 'False') == 'True',
            },
            'report': {
                'required_on_checkout': ICP.get_param('waqf.mobile.report_required', 'False') == 'True',
                'min_photos':           int(ICP.get_param('waqf.mobile.min_photos', 1)),
            },
            'notifications': {
                'pending_worklogs':     ICP.get_param('waqf.mobile.notify_pending', 'True') == 'True',
                'no_visit_alert_days':  int(ICP.get_param('waqf.mobile.no_visit_alert_days', 2)),
            },
            'app': {
                'min_version':    ICP.get_param('waqf.mobile.min_version', '1.0.0'),
                'maintenance':    ICP.get_param('waqf.mobile.maintenance', 'False') == 'True',
                'maintenance_msg': ICP.get_param('waqf.mobile.maintenance_msg', ''),
            },
        }
