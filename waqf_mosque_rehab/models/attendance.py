from odoo import models, fields, api, _
from datetime import date, timedelta


class MosqueDashboard(models.Model):
    _name = 'mosque.dashboard'
    _description = 'Project Dashboard'

    @api.model
    def get_dashboard_data(self):
        """
        Main endpoint for the executive dashboard.
        Returns all KPIs and mosque status data.
        """
        Mosque = self.env['mosque.mosque']
        mosques = Mosque.search([('active', '=', True)])

        today = date.today()

        # ── Summary cards ─────────────────────────────────────────
        total = len(mosques)
        by_state = {}
        for m in mosques:
            by_state[m.state] = by_state.get(m.state, 0) + 1

        on_track  = mosques.filtered(lambda m: m.overall_kpi >= 70)
        at_risk   = mosques.filtered(lambda m: 50 <= m.overall_kpi < 70)
        critical  = mosques.filtered(lambda m: m.overall_kpi < 50)
        delayed   = mosques.filtered(lambda m: m.days_delay > 0)

        # ── Financial summary ─────────────────────────────────────
        total_contract_value = sum(mosques.mapped('contract_value'))
        total_boq_value      = sum(mosques.mapped('total_boq_value'))
        total_certified      = sum(mosques.mapped('certified_amount'))
        total_co_value       = sum(mosques.mapped('change_order_value'))

        # ── Visit compliance this week ─────────────────────────────
        week_start = today - timedelta(days=today.weekday())
        AttLog = self.env['mosque.attendance']
        visits_this_week = AttLog.search_count([
            ('check_in', '>=', week_start.strftime('%Y-%m-%d')),
            ('is_validated', '=', True),
            ('visit_type', '=', 'field'),
        ])

        # ── Certificates pending ──────────────────────────────────
        Cert = self.env['mosque.certificate']
        certs_pending_consultant = Cert.search_count([
            ('state', '=', 'consultant_review')])
        certs_pending_waqf = Cert.search_count([
            ('state', 'in', ['waqf_review'])])

        # ── Per-mosque data ───────────────────────────────────────
        mosque_list = []
        for m in mosques.sorted('overall_kpi'):
            mosque_list.append({
                'id':                m.id,
                'name':              m.name,
                'code':              m.code,
                'city':              m.city,
                'package':           m.package_id.name or '',
                'phase':             m.phase or '',
                'state':             m.state,
                'state_label':       dict(m._fields['state'].selection).get(m.state, ''),
                'overall_kpi':       round(m.overall_kpi, 1),
                'kpi_color':         m.kpi_color,
                'financial_pct':     round(m.financial_progress, 1),
                'time_pct':          round(m.time_progress, 1),
                'visit_compliance':  round(m.visit_compliance, 1),
                'days_delay':        m.days_delay,
                'contract_value':    m.contract_value,
                'certified_amount':  m.certified_amount,
                'total_boq_value':   m.total_boq_value,
                'engineer':          m.resident_engineer_id.name or '—',
                'planned_end':       m.planned_end.strftime('%Y-%m-%d') if m.planned_end else '',
                'cert_count':        m.certificate_count,
                'supervision_count': m.supervision_count,
                'change_orders':     m.change_order_count,
                'boq_count':         m.boq_count,
            })

        # ── Package progress ──────────────────────────────────────
        packages = self.env['mosque.package'].search([])
        package_data = []
        for pkg in packages:
            pkg_mosques = pkg.mosque_ids
            package_data.append({
                'name': pkg.name,
                'code': pkg.code,
                'phase': pkg.phase,
                'total': len(pkg_mosques),
                'avg_kpi': round(
                    sum(pkg_mosques.mapped('overall_kpi')) / len(pkg_mosques), 1
                ) if pkg_mosques else 0,
                'avg_financial': round(
                    sum(pkg_mosques.mapped('financial_progress')) / len(pkg_mosques), 1
                ) if pkg_mosques else 0,
            })

        # ── Recent supervisions ───────────────────────────────────
        recent_supervisions = self.env['mosque.supervision'].search(
            [('state', '=', 'submitted')], limit=10, order='report_date desc')
        recent_sup_data = [{
            'mosque': s.mosque_id.name,
            'engineer': s.engineer_id.name,
            'date': s.report_date.strftime('%Y-%m-%d'),
            'type': s.report_type,
            'ncr': s.ncr_count,
        } for s in recent_supervisions]

        return {
            'today': today.strftime('%Y-%m-%d'),
            'summary': {
                'total_mosques':      total,
                'on_track':           len(on_track),
                'at_risk':            len(at_risk),
                'critical':           len(critical),
                'delayed':            len(delayed),
                'by_state':           by_state,
                'total_contract':     total_contract_value,
                'total_boq':          total_boq_value,
                'total_certified':    total_certified,
                'total_co':           total_co_value,
                'overall_pct':        round(total_certified / total_boq_value * 100, 1)
                                      if total_boq_value else 0,
                'visits_this_week':   visits_this_week,
                'certs_pending_consultant': certs_pending_consultant,
                'certs_pending_waqf':       certs_pending_waqf,
            },
            'mosques':    mosque_list,
            'packages':   package_data,
            'recent_supervisions': recent_sup_data,
        }
