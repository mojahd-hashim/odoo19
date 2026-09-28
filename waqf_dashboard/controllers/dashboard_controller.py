from odoo import http
from odoo.http import request
import json

from .helpers import mosque_domain, mosque_perf, onsite_list, riyadh_today


class WaqfDashboardController(http.Controller):

    @http.route('/dashboard', type='http', auth='user', website=True)
    def dashboard(self, **kwargs):
        env = request.env
        company = env.user.company_id
        config = env['res.config.settings'].sudo().get_dashboard_config()
        today = riyadh_today()
        base_domain = mosque_domain(env)

        # ── Packages (phases) with mosques ─────────────────────
        packages_data = []
        for pkg in env['mosque.package'].sudo().search([], order='sequence'):
            mosques = pkg.mosque_ids.filtered_domain(base_domain) if base_domain else pkg.mosque_ids
            perfs = [(m, mosque_perf(m, today)) for m in mosques]
            boq_total = sum(p['boq_value'] for _m, p in perfs)
            executed = sum(p['executed_value'] for _m, p in perfs)
            is_current = is_past = is_future = False
            if pkg.planned_start and pkg.planned_end:
                is_current = pkg.planned_start <= today <= pkg.planned_end
                is_past = pkg.planned_end < today
                is_future = pkg.planned_start > today
            packages_data.append({
                'id': pkg.id, 'code': pkg.code, 'name': pkg.name,
                'mosque_count': len(mosques),
                'avg_kpi': round(executed / boq_total * 100, 1) if boq_total else 0,
                'delayed_count': sum(1 for _m, p in perfs if p['status'] == 'critical'),
                'planned_start': str(pkg.planned_start) if pkg.planned_start else '',
                'planned_end': str(pkg.planned_end) if pkg.planned_end else '',
                'is_current': is_current, 'is_past': is_past, 'is_future': is_future,
                'mosques': [{
                    'id': m.id, 'code': m.code, 'name': m.name,
                    'state': m.state,
                    'overall_kpi': p['actual_pct'],
                    'actual_pct': p['actual_pct'],
                    'planned_pct': p['planned_pct'],
                    'days_delay': p['days_delay'],
                    'status': p['status'],
                } for m, p in perfs],
            })

        on_site = onsite_list(env)
        mosque_count = env['mosque.mosque'].sudo().search_count(base_domain)

        return request.render('waqf_dashboard.tmpl_dashboard', {
            'company': company,
            'config': config,
            'packages_json': json.dumps(packages_data),
            'on_site': on_site,
            'on_site_count': len(on_site),
            'user': env.user,
            'has_ai_module': 'waqf.ai.snapshot.run' in env,
            'mosque_count': mosque_count,
        })

    @http.route('/dashboard/settings', type='http', auth='user', website=True)
    def dashboard_settings(self, **kwargs):
        return request.redirect('/odoo/settings?searchTerms=Waqf')
