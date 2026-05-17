from odoo import http
from odoo.http import request
from datetime import date, datetime
import json


class WaqfDashboardController(http.Controller):

    @http.route('/dashboard', type='http', auth='user', website=True)
    def dashboard(self, **kwargs):
        company = request.env.user.company_id
        config  = request.env['res.config.settings'].sudo().get_dashboard_config()
        today   = date.today()

        # ── Packages with mosques ──────────────────────────────
        packages = request.env['mosque.package'].sudo().search([], order='sequence')
        packages_data = []
        for pkg in packages:
            mosques = pkg.mosque_ids.filtered(lambda m: not m.is_demo)
            avg_kpi = sum(mosques.mapped('overall_kpi')) / len(mosques) if mosques else 0
            is_current = is_past = is_future = False
            if pkg.planned_start and pkg.planned_end:
                is_current = pkg.planned_start <= today <= pkg.planned_end
                is_past    = pkg.planned_end < today
                is_future  = pkg.planned_start > today
            packages_data.append({
                'id': pkg.id, 'code': pkg.code, 'name': pkg.name,
                'mosque_count': len(mosques), 'avg_kpi': round(avg_kpi, 1),
                'planned_start': str(pkg.planned_start) if pkg.planned_start else '',
                'planned_end':   str(pkg.planned_end)   if pkg.planned_end   else '',
                'is_current': is_current, 'is_past': is_past, 'is_future': is_future,
                'mosques': [{
                    'id': m.id, 'code': m.code, 'name': m.name,
                    'overall_kpi': round(m.overall_kpi, 1),
                    'state': m.state, 'days_delay': m.days_delay,
                    'kpi_color': ('green' if m.overall_kpi >= 70 else
                                  'yellow' if m.overall_kpi >= 50 else
                                  'red' if m.overall_kpi > 0 else 'gray'),
                } for m in mosques],
            })

        # ── On-site consultants ────────────────────────────────
        today_start = datetime.combine(today, datetime.min.time())
        active_att  = request.env['mosque.attendance'].sudo().search([
            ('check_in', '>=', today_start), ('check_out', '=', False)])
        on_site = []
        for att in active_att:
            elapsed = (datetime.now() - att.check_in).total_seconds() / 3600 if att.check_in else 0
            on_site.append({
                'name':    att.engineer_id.name if att.engineer_id else '',
                'mosque':  att.mosque_id.name   if att.mosque_id   else '',
                'code':    att.mosque_id.code   if att.mosque_id   else '',
                'checkin': att.check_in.strftime('%H:%M') if att.check_in else '',
                'elapsed': round(elapsed, 1),
            })

        # ── Summary KPIs ───────────────────────────────────────
        all_m = request.env['mosque.mosque'].sudo().search([('is_demo', '=', False)])
        summary = {
            'total_value':   sum(all_m.mapped('contract_value')),
            'avg_kpi':       round(sum(all_m.mapped('overall_kpi')) / len(all_m), 1) if all_m else 0,
            'delayed':       len(all_m.filtered(lambda m: m.days_delay > 0)),
            'pending_certs': request.env['mosque.certificate'].sudo().search_count(
                [('state', 'in', ['submitted', 'consultant_approved'])]),
            'pending_cos':   request.env['mosque.change.order'].sudo().search_count(
                [('state', '=', 'review')]),
            'mosque_count':  len(all_m),
        }

        active_stream = request.env['waqf.live.stream'].sudo().get_active_stream()
        has_ai_module = 'waqf.ai.snapshot.run' in request.env

        return request.render('waqf_dashboard.tmpl_dashboard', {
            'company':       company,
            'config':        config,
            'packages':      packages,
            'packages_json': json.dumps(packages_data),
            'active_stream': active_stream,
            'on_site':       on_site,
            'on_site_count': len(on_site),
            'summary':       summary,
            'user':          request.env.user,
            'has_ai_module': has_ai_module,  # ← أضف
            'mosque_count': len(all_m),
        })

    @http.route('/dashboard/settings', type='http', auth='user', website=True)
    def dashboard_settings(self, **kwargs):
        return request.redirect('/odoo/settings?searchTerms=Waqf')