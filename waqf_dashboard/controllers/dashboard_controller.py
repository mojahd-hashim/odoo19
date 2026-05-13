from odoo import http
from odoo.http import request


class WaqfDashboardController(http.Controller):

    @http.route('/dashboard', type='http', auth='user', website=True)
    def dashboard(self, **kwargs):
        """Main dashboard page."""
        # Company info
        company = request.env.user.company_id
        ICP     = request.env['ir.config_parameter'].sudo()

        # App config
        config = request.env['res.config.settings'].sudo().get_dashboard_config()

        # Packages summary for sidebar
        packages = request.env['mosque.package'].sudo().search(
            [], order='sequence')

        # Active stream notification
        active_stream = request.env['waqf.live.stream'].sudo().get_active_stream()

        # Currently on-site consultants
        from datetime import date, datetime, timedelta
        today_start = datetime.combine(date.today(), datetime.min.time())
        active_attendance = request.env['mosque.attendance'].sudo().search([
            ('check_in',  '>=', today_start),
            ('check_out', '=',  False),
        ])

        on_site = []
        for att in active_attendance:
            on_site.append({
                'name':    att.engineer_id.name if att.engineer_id else '',
                'mosque':  att.mosque_id.name if att.mosque_id else '',
                'code':    att.mosque_id.code if att.mosque_id else '',
                'checkin': str(att.check_in.strftime('%H:%M')) if att.check_in else '',
            })

        return request.render('waqf_dashboard.tmpl_dashboard', {
            'company':       company,
            'config':        config,
            'packages':      packages,
            'active_stream': active_stream,
            'on_site':       on_site,
            'user':          request.env.user,
        })

    @http.route('/dashboard/settings', type='http', auth='user', website=True)
    def dashboard_settings(self, **kwargs):
        """Redirect to Odoo settings for dashboard config."""
        return request.redirect('/odoo/settings?searchTerms=Waqf')