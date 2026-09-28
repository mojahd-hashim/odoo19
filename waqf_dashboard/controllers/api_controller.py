import json
from odoo import http
from odoo.http import request
from datetime import date, datetime, timedelta

from .helpers import (
    mosque_domain, mosque_perf, onsite_list, current_package,
    riyadh_today, fmt_riyadh, to_riyadh,
)


def _json(data):
    return request.make_response(
        json.dumps(data, ensure_ascii=False, default=str),
        headers=[('Content-Type', 'application/json')]
    )


class WaqfDashboardAPI(http.Controller):

    # ══════════════════════════════════════════════════════
    # EXECUTIVE SUMMARY — KPI Strip
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/summary', type='http', auth='user', csrf=False)
    def api_summary(self, **kw):
        """Global counters. Progress KPIs are computed client-side from
        /dashboard/api/mosques so they follow the selected phase."""
        env = request.env
        Cert = env['mosque.certificate'].sudo()
        CO = env['mosque.change.order'].sudo()

        pending = {
            'certs': Cert.search_count([('state', 'in', ['submitted', 'consultant_approved'])]),
            'cos': CO.search_count([('state', '=', 'review')]),
            'work_orders': 0,
            'claims': 0,
        }
        if 'contractor.work.order' in env:
            pending['work_orders'] = env['contractor.work.order'].sudo().search_count(
                [('state', 'in', ['submitted', 'delivered'])])
        if 'waqf.payment.claim' in env:
            pending['claims'] = env['waqf.payment.claim'].sudo().search_count(
                [('state', 'in', ['submitted', 'reviewed'])])

        cos = CO.search([('state', 'not in', ['rejected'])])
        co_value = sum(cos.mapped('amount'))
        co_pending_value = sum(cos.filtered(lambda c: c.state == 'review').mapped('amount'))

        pkg = current_package(env)
        return _json({
            'pending': pending,
            'pending_total': sum(pending.values()),
            'co_value': co_value,
            'co_pending_value': co_pending_value,
            'onsite_count': len(onsite_list(env)),
            'current_package_id': pkg.id if pkg else None,
            'current_package_name': pkg.name if pkg else '',
            'today': str(riyadh_today()),
        })

    # ══════════════════════════════════════════════════════
    # SMART ALERTS — from AI Risk Center
    # ══════════════════════════════════════════════════════
    # alert_type → dashboard filter group
    ALERT_GROUPS = {
        'financial': 'financial', 'payment_execution_impact': 'financial',
        'change_order': 'financial', 'approval': 'financial',
        'delay': 'delay', 'boq': 'delay', 'silent_project': 'delay',
        'contractor': 'delay', 'risk': 'delay',
        'quality': 'quality', 'supervision': 'quality', 'data_conflict': 'quality',
    }
    SEV_ORDER = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}

    @http.route('/dashboard/api/alerts', type='http', auth='user', csrf=False)
    def api_alerts(self, **kw):
        """
        Primary source: waqf.ai.alert (AI Risk Center) — only alerts that are
        still open and belong to the latest successful run (older runs keep
        stale 'new' alerts forever), de-duplicated per mosque/type/title.
        Fallback: rule-based alerts computed from live data.
        """
        env = request.env
        has_ai = 'waqf.ai.alert' in env
        alerts = []
        last_run_at = ''

        if has_ai:
            Alert = env['waqf.ai.alert'].sudo()
            domain = [('status', 'in', ['new', 'acknowledged', 'in_progress'])]
            last_run = env['waqf.ai.snapshot.run'].sudo().search(
                [('status', 'in', ['done', 'done_with_ai_error'])],
                order='run_datetime desc', limit=1)
            if last_run:
                domain.append(('run_id', 'in', [last_run.id, False]))
                last_run_at = fmt_riyadh(last_run.run_datetime, '%Y-%m-%d %H:%M')

            seen = set()
            for a in Alert.search(domain, order='priority_score desc, create_date desc', limit=200):
                key = (a.mosque_id.id, a.alert_type, a.title)
                if key in seen:
                    continue
                seen.add(key)
                alerts.append({
                    'id': a.id,
                    'title': a.title,
                    'description': a.summary or '',
                    'root_cause': a.root_cause or '',
                    'recommendation': a.recommendation or '',
                    'severity': a.severity,
                    'category': a.alert_type,
                    'group': self.ALERT_GROUPS.get(a.alert_type, 'delay'),
                    'source': a.source,
                    'confidence': round((a.confidence or 0) * 100),
                    'mosque_id': a.mosque_id.id or None,
                    'mosque_name': a.mosque_id.name or a.contractor or '',
                    'mosque_code': a.mosque_id.code or '',
                    'state': a.status,
                    'created_at': fmt_riyadh(a.create_date, '%Y-%m-%d %H:%M'),
                })

        from_ai = bool(alerts)
        if not alerts:
            alerts = self._computed_alerts(env)

        alerts.sort(key=lambda a: self.SEV_ORDER.get(a['severity'], 9))
        counts = {'all': len(alerts), 'critical': 0, 'financial': 0, 'delay': 0, 'quality': 0}
        for a in alerts:
            if a['severity'] == 'critical':
                counts['critical'] += 1
            counts[a['group']] = counts.get(a['group'], 0) + 1

        return _json({
            'alerts': alerts[:60],
            'total': len(alerts),
            'counts': counts,
            'source': 'ai_center' if from_ai else 'computed',
            'last_run': last_run_at,
        })

    def _computed_alerts(self, env):
        """Rule-based alerts from live data (used when the AI center has none)."""
        today = riyadh_today()
        alerts = []

        def add(sev, group, title, desc, m=None, rec=''):
            alerts.append({
                'id': len(alerts) + 1, 'severity': sev, 'category': group, 'group': group,
                'title': title, 'description': desc, 'root_cause': '', 'recommendation': rec,
                'source': 'computed', 'confidence': 0,
                'mosque_id': m.id if m else None,
                'mosque_name': m.name if m else '', 'mosque_code': m.code if m else '',
                'state': 'new', 'created_at': '',
            })

        week_ago = datetime.utcnow() - timedelta(days=7)
        Att = env['mosque.attendance'].sudo()
        for m in env['mosque.mosque'].sudo().search(mosque_domain(env)):
            p = mosque_perf(m, today)
            if p['status'] == 'critical':
                if p['days_delay'] > 0:
                    add('critical', 'delay', f'{m.name} — متأخر {p["days_delay"]} يوم',
                        f'الإنجاز الفعلي {p["actual_pct"]}% وانتهت المدة المخططة.', m,
                        'اجتماع عاجل مع المقاول واعتماد خطة تعافٍ بجدول زمني.')
                else:
                    add('critical', 'delay', f'{m.name} — انحراف كبير عن الخطة',
                        f'الفعلي {p["actual_pct"]}% مقابل المخطط {p["planned_pct"]}%.', m,
                        'مراجعة الموارد في الموقع وأوامر العمل المتوقفة.')
            elif p['status'] == 'warning':
                add('high', 'delay', f'{m.name} — تأخر عن الخطة',
                    f'الفعلي {p["actual_pct"]}% مقابل المخطط {p["planned_pct"]}%.', m)
            if m.state == 'active' and not Att.search_count(
                    [('mosque_id', '=', m.id), ('check_in', '>=', week_ago)]):
                add('medium', 'quality', f'{m.name} — لا زيارات إشرافية منذ 7 أيام',
                    'لم يُسجَّل حضور للاستشاري خلال الأسبوع الماضي.', m,
                    'جدولة زيارة ميدانية وتوثيقها بالموقع الجغرافي.')

        cutoff = datetime.utcnow() - timedelta(days=7)
        for c in env['mosque.certificate'].sudo().search(
                [('state', 'in', ['submitted', 'consultant_approved']), ('create_date', '<', cutoff)]):
            add('high', 'financial', f'مستخلص #{c.cert_number} معلّق منذ أكثر من 7 أيام',
                f'{c.mosque_id.name or ""} · {round(c.certified_amount or 0):,} ريال', c.mosque_id)
        for co in env['mosque.change.order'].sudo().search(
                [('state', '=', 'review'), ('amount', '>', 100000)]):
            add('high', 'financial', f'أمر تغيير {co.name} بقيمة {round(co.amount):,} ريال',
                co.reason or '', co.mosque_id)
        return alerts

    # ══════════════════════════════════════════════════════
    # AI INSIGHTS — Executive Summaries
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/ai_insights', type='http', auth='user', csrf=False)
    def api_ai_insights(self, mosque_id=None, **kw):
        """
        Returns AI-generated insights from waqf.ai.prediction / waqf.ai.phase.insight
        Falls back to rule-based insights if AI module absent.
        """
        has_ai = 'waqf.ai.prediction' in request.env
        insights = []
        last_updated = ''

        if has_ai:
            Pred = request.env['waqf.ai.prediction'].sudo()
            Phase = request.env['waqf.ai.phase.insight'].sudo()

            domain = []
            if mosque_id:
                domain.append(('mosque_id', '=', int(mosque_id)))

            # من waqf.ai.prediction — الحقول الصحيحة
            for p in Pred.search(domain, limit=8):
                type_map = {
                    'expected_delay': 'risk',
                    'financial_overrun': 'risk',
                    'quality_risk': 'risk',
                    'supervision_gap': 'warning',
                    'approval_bottleneck': 'action',
                    'phase_delay': 'risk',
                }
                icon_map = {
                    'expected_delay': '⏱',
                    'financial_overrun': '💰',
                    'quality_risk': '🔍',
                    'supervision_gap': '👷',
                    'approval_bottleneck': '📋',
                    'phase_delay': '📅',
                }
                insights.append({
                    'type': type_map.get(p.prediction_type, 'info'),
                    'icon': icon_map.get(p.prediction_type, '📊'),
                    'title': dict(p._fields['prediction_type'].selection).get(p.prediction_type, p.prediction_type),
                    'body': p.prediction_text or p.recommendation or '',
                    'priority': 1 if p.probability > 0.7 else 2 if p.probability > 0.4 else 3,
                    'mosque_id': p.mosque_id.id if p.mosque_id else None,
                    'mosque_name': p.mosque_id.name if p.mosque_id else '',
                    'action_label': p.recommendation[:25] + '...' if p.recommendation and len(
                        p.recommendation) > 25 else (p.recommendation or ''),
                })

            # من waqf.ai.phase.insight — الحقول الصحيحة
            for ph in Phase.search([], limit=3):
                health_icon = {'good': '✅', 'watch': '⚠️', 'risk': '🔴', 'critical': '🚨'}.get(ph.phase_health, '📦')
                insights.append({
                    'type': 'phase',
                    'icon': health_icon,
                    'title': f'ملخص المرحلة — {ph.phase_id.name if ph.phase_id else ""}',
                    'body': ph.overall_summary or '',
                    'priority': 99,
                    'mosque_id': None,
                    'mosque_name': '',
                    'action_label': '',
                })

            # Last snapshot time
            SnapshotRun = request.env['waqf.ai.snapshot.run'].sudo()
            last_run = SnapshotRun.search(
                [('status', 'in', ['done', 'done_with_ai_error'])],
                order='run_datetime desc', limit=1)
            if last_run:
                last_updated = str(last_run.run_datetime)

        else:
            # ── Rule-based fallback insights ──────────────
            Mosque = request.env['mosque.mosque'].sudo()
            mosques = Mosque.search([('is_demo', '=', False)])

            if mosque_id:
                mosques = Mosque.browse(int(mosque_id))

            # Worst KPI
            worst = mosques.sorted('overall_kpi')
            if worst:
                m = worst[0]
                insights.append({
                    'type': 'risk', 'icon': '🔴', 'priority': 1,
                    'title': 'خطر تعثر فوري',
                    'body': (f'<strong>{m.name}</strong> يسجل أدنى KPI بنسبة '
                             f'{round(m.overall_kpi)}% مع تأخير {m.days_delay} يوم. '
                             f'يُنصح بعقد اجتماع طارئ مع المقاول وإصدار إنذار رسمي.'),
                    'mosque_id': m.id, 'mosque_name': m.name,
                    'action_label': 'فتح تفاصيل المسجد',
                })

            # Financial deviation
            over_budget = mosques.filtered(
                lambda m: m.financial_progress > m.time_progress + 15)
            if over_budget:
                insights.append({
                    'type': 'risk', 'icon': '📊', 'priority': 2,
                    'title': 'انحراف مالي متسارع',
                    'body': (f'{len(over_budget)} مسجد ينفق أسرع من معدل الإنجاز الزمني '
                             f'بفارق يتجاوز 15%. السبب الأرجح أوامر تغيير تُنفَّذ قبل الاعتماد.'),
                    'mosque_id': None, 'mosque_name': '',
                    'action_label': '',
                })

            # Best performer
            best = mosques.sorted('overall_kpi', reverse=True)
            if best and best[0].overall_kpi > 75:
                m = best[0]
                insights.append({
                    'type': 'opportunity', 'icon': '✅', 'priority': 3,
                    'title': 'أفضل مقاول أداءً',
                    'body': (f'<strong>{m.contractor or m.name}</strong> يحقق KPI '
                             f'{round(m.overall_kpi)}% مع الالتزام الزمني. '
                             f'يُنصح بتحليل أسلوبه وتطبيقه على باقي المقاولين.'),
                    'mosque_id': m.id, 'mosque_name': m.name,
                    'action_label': '',
                })

            # Pending approvals
            Cert = request.env['mosque.certificate'].sudo()
            pending = Cert.search_count(
                [('state', 'in', ['submitted', 'consultant_approved'])])
            if pending > 0:
                total_val = sum(Cert.search(
                    [('state', 'in', ['submitted', 'consultant_approved'])]
                ).mapped('certified_amount'))
                insights.append({
                    'type': 'action', 'icon': '🎯', 'priority': 4,
                    'title': 'قرار اعتماد عاجل',
                    'body': (f'{pending} مستخلص بإجمالي '
                             f'{round(total_val / 1000):,} ألف ريال '
                             f'بانتظار الاعتماد. التأخير يُعيق استمرارية التنفيذ.'),
                    'mosque_id': None, 'mosque_name': '',
                    'action_label': 'مراجعة المستخلصات',
                })

        return _json({
            'insights': insights,
            'last_updated': last_updated,
            'source': 'ai_center' if has_ai else 'computed',
        })

    # ══════════════════════════════════════════════════════
    # RISK MATRIX
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/risk_matrix', type='http', auth='user', csrf=False)
    def api_risk_matrix(self, **kw):
        """
        Returns risk matrix data per mosque.
        X = impact (0-100), Y = probability (0-100), size = contract_value
        """
        has_ai = 'waqf.ai.mosque.snapshot' in request.env
        points = []

        if has_ai:
            Snap = request.env['waqf.ai.mosque.snapshot'].sudo()
            # نأخذ آخر run فقط
            last_run = request.env['waqf.ai.snapshot.run'].sudo().search(
                [('status', 'in', ['done', 'done_with_ai_error'])],
                order='run_datetime desc', limit=1)

            domain = [('run_id', '=', last_run.id)] if last_run else []

            for s in Snap.search(domain):
                # نحسب impact و probability من الحقول الموجودة
                impact = max(0, min(100, 100 - s.overall_kpi))

                probability = min(100, (
                        (s.days_delay * 1.5) +
                        (s.pending_certificates_count * 5) +
                        (s.ncr_count_30d * 3) +
                        (s.days_since_last_report * 0.5 if s.days_since_last_report < 999 else 30) +
                        (s.rejected_tasks_count * 4) +
                        (s.blocked_tasks_count * 3)
                ))

                risk_level = (
                    'critical' if impact > 60 and probability > 60 else
                    'high' if impact > 45 or probability > 45 else
                    'medium' if impact > 30 or probability > 30 else
                    'low'
                )

                points.append({
                    'mosque_id': s.mosque_id.id,
                    'mosque_name': s.mosque_name or s.mosque_id.name,
                    'mosque_code': s.mosque_code or s.mosque_id.code,
                    'impact': round(impact, 1),
                    'probability': round(probability, 1),
                    'size': s.contract_value,
                    'kpi': round(s.overall_kpi, 1),
                    'risk_level': risk_level,
                })
        else:
            # Fallback: derive from KPI + delay
            for m in request.env['mosque.mosque'].sudo().search(
                    [('is_demo', '=', False)]):
                if m.overall_kpi <= 0:
                    continue
                # Impact = inverse of KPI
                impact = max(0, min(100, 100 - m.overall_kpi))
                # Probability = based on delay + financial deviation
                fin_dev = abs(m.financial_progress - m.time_progress)
                prob = max(0, min(100, (m.days_delay / 2) + fin_dev))
                risk_lvl = ('critical' if impact > 60 and prob > 60 else
                            'high' if impact > 45 or prob > 45 else
                            'medium' if impact > 30 or prob > 30 else 'low')
                points.append({
                    'mosque_id': m.id, 'mosque_name': m.name, 'mosque_code': m.code,
                    'impact': round(impact, 1), 'probability': round(prob, 1),
                    'size': m.contract_value,
                    'kpi': round(m.overall_kpi, 1),
                    'risk_level': risk_lvl,
                })

        return _json({'points': points})

    # ══════════════════════════════════════════════════════
    # FORECAST ENGINE
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/forecast', type='http', auth='user', csrf=False)
    def api_forecast(self, **kw):
        has_ai = 'waqf.ai.mosque.snapshot' in request.env
        rows = []

        if has_ai:
            Snap = request.env['waqf.ai.mosque.snapshot'].sudo()
            last_run = request.env['waqf.ai.snapshot.run'].sudo().search(
                [('status', 'in', ['done', 'done_with_ai_error'])],
                order='run_datetime desc', limit=1)

            domain = [('run_id', '=', last_run.id)] if last_run else []

            for s in Snap.search(domain, order='days_delay desc', limit=12):
                m = s.mosque_id
                if not m.planned_end:
                    continue
                variance = s.days_delay or 0
                forecast = m.planned_end + timedelta(days=variance)
                confidence = max(20, min(95, 95 - variance * 1.5))
                rows.append({
                    'mosque_id': m.id,
                    'mosque_name': s.mosque_name or m.name,
                    'mosque_code': s.mosque_code or m.code,
                    'planned_finish': str(m.planned_end),
                    'forecast_finish': str(forecast),
                    'variance_days': variance,
                    'confidence_pct': round(confidence, 0),
                    'is_at_risk': variance > 0,
                })
        else:
            # Fallback: linear projection
            for m in request.env['mosque.mosque'].sudo().search(
                    [('is_demo', '=', False),
                     ('planned_end', '!=', False),
                     ('state', 'in', ['mobilizing', 'active'])]):
                variance = m.days_delay
                confidence = max(20, min(95, 95 - variance * 1.5))
                if m.planned_end:
                    from datetime import timedelta as td
                    forecast = m.planned_end + td(days=variance)
                else:
                    forecast = None
                rows.append({
                    'mosque_id': m.id,
                    'mosque_name': m.name,
                    'mosque_code': m.code,
                    'planned_finish': str(m.planned_end) if m.planned_end else '',
                    'forecast_finish': str(forecast) if forecast else '',
                    'variance_days': variance,
                    'confidence_pct': round(confidence, 0),
                    'is_at_risk': variance > 0,
                })
            rows.sort(key=lambda r: r['variance_days'], reverse=True)
            rows = rows[:10]

        return _json({'rows': rows})

    # ══════════════════════════════════════════════════════
    # CONTRACTOR INTELLIGENCE
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/contractors', type='http', auth='user', csrf=False)
    def api_contractors(self, **kw):
        Mosque = request.env['mosque.mosque'].sudo()
        CO = request.env['mosque.change.order'].sudo()
        Sup = request.env['mosque.supervision'].sudo()

        # Group by contractor
        contractor_data = {}
        for m in Mosque.search([('is_demo', '=', False),
                                ('contractor', '!=', False)]):
            c = m.contractor
            if c not in contractor_data:
                contractor_data[c] = {
                    'name': c, 'mosques': [], 'kpis': [],
                    'delays': [], 'co_count': 0, 'ncr_total': 0,
                }
            contractor_data[c]['mosques'].append(m.id)
            contractor_data[c]['kpis'].append(m.overall_kpi)
            contractor_data[c]['delays'].append(m.days_delay)

        # Enrich with COs and NCRs
        for co in CO.search([('state', 'not in', ['rejected'])]):
            if co.mosque_id and co.mosque_id.contractor:
                c = co.mosque_id.contractor
                if c in contractor_data:
                    contractor_data[c]['co_count'] += 1

        for sup in Sup.search([('ncr_count', '>', 0)]):
            if sup.mosque_id and sup.mosque_id.contractor:
                c = sup.mosque_id.contractor
                if c in contractor_data:
                    contractor_data[c]['ncr_total'] += sup.ncr_count

        result = []
        for c, d in contractor_data.items():
            avg_kpi = sum(d['kpis']) / len(d['kpis']) if d['kpis'] else 0
            avg_delay = sum(d['delays']) / len(d['delays']) if d['delays'] else 0
            result.append({
                'name': c,
                'mosque_count': len(d['mosques']),
                'avg_kpi': round(avg_kpi, 1),
                'avg_delay': round(avg_delay, 1),
                'co_count': d['co_count'],
                'ncr_total': d['ncr_total'],
                'rating': ('good' if avg_kpi >= 70 else
                           'warn' if avg_kpi >= 50 else 'bad'),
            })

        result.sort(key=lambda r: r['avg_kpi'], reverse=True)
        return _json({'contractors': result})

    # ══════════════════════════════════════════════════════
    # QUALITY INTELLIGENCE
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/quality', type='http', auth='user', csrf=False)
    def api_quality(self, **kw):
        Sup = request.env['mosque.supervision'].sudo()
        sups = Sup.search([])

        ncr_total = sum(sups.mapped('ncr_count'))
        safety_inc = sum(sups.mapped('safety_incidents'))
        itp_check = sum(sups.mapped('itp_hold_points_checked'))
        itp_appr = sum(sups.mapped('itp_hold_points_approved'))
        itp_rate = round(itp_appr / itp_check * 100, 1) if itp_check else 0

        # Failed inspections
        failed_itp = itp_check - itp_appr

        # Open issues from supervision
        open_issues = len(sups.filtered(lambda s: s.issues))

        # Quality score: weighted formula
        ncr_score = max(0, 100 - ncr_total * 2)
        safety_score = max(0, 100 - safety_inc * 5)
        itp_score = itp_rate
        quality_score = round(ncr_score * 0.4 + safety_score * 0.3 + itp_score * 0.3, 1)

        rating = ('excellent' if quality_score >= 85 else
                  'good' if quality_score >= 70 else
                  'warning' if quality_score >= 55 else 'critical')

        return _json({
            'quality_score': quality_score,
            'rating': rating,
            'ncr_total': ncr_total,
            'safety_incidents': safety_inc,
            'failed_inspections': failed_itp,
            'open_issues': open_issues,
            'itp_rate': itp_rate,
        })

    # ══════════════════════════════════════════════════════
    # MOSQUES LIST (for heatmap + search)
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/mosques', type='http', auth='user', csrf=False)
    def api_mosques(self, **kw):
        env = request.env
        today = riyadh_today()
        mosques = env['mosque.mosque'].sudo().search(mosque_domain(env), order='code')

        onsite = {}
        for p in onsite_list(env):
            if p['mosque_id']:
                onsite.setdefault(p['mosque_id'], []).append(p['name'])

        streams = {}
        for st in env['waqf.live.stream'].sudo().search(
                [('is_active', '=', True), ('mosque_id', '!=', False)]):
            streams.setdefault(st.mosque_id.id, st.stream_url)

        result = []
        for m in mosques:
            perf = mosque_perf(m, today)
            result.append({
                'id': m.id,
                'code': m.code,
                'name': m.name,
                'city': m.city,
                'district': m.district or '',
                'state': m.state,
                'contractor': m.contractor or '',
                'package': m.package_id.name if m.package_id else '',
                'package_id': m.package_id.id if m.package_id else 0,
                'overall_kpi': round(m.overall_kpi, 1),
                'financial_pct': perf['actual_pct'],
                'time_pct': perf['planned_pct'],
                'planned_start': str(m.planned_start) if m.planned_start else '',
                'planned_end': str(m.planned_end) if m.planned_end else '',
                'lat': m.latitude,
                'lng': m.longitude,
                'onsite': onsite.get(m.id, []),
                'stream_url': streams.get(m.id, ''),
                **perf,
            })
        return _json(result)

    # ══════════════════════════════════════════════════════
    # PACKAGES (Gantt)
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/packages', type='http', auth='user', csrf=False)
    def api_packages(self, **kw):
        packages = request.env['mosque.package'].sudo().search([], order='sequence')
        today = date.today()
        result = []

        for pkg in packages:
            mosques = pkg.mosque_ids.filtered(lambda m: not m.is_demo)
            avg_kpi = sum(mosques.mapped('overall_kpi')) / len(mosques) if mosques else 0
            avg_time = sum(mosques.mapped('time_progress')) / len(mosques) if mosques else 0
            delayed = len(mosques.filtered(lambda m: m.days_delay > 0))

            is_current = is_past = is_future = False
            expected_pct = 0
            if pkg.planned_start and pkg.planned_end:
                is_current = pkg.planned_start <= today <= pkg.planned_end
                is_past = pkg.planned_end < today
                is_future = pkg.planned_start > today
                total_days = (pkg.planned_end - pkg.planned_start).days
                elapsed = (today - pkg.planned_start).days
                if total_days > 0:
                    expected_pct = min(100, round(elapsed / total_days * 100, 1))

            result.append({
                'id': pkg.id,
                'code': pkg.code,
                'name': pkg.name,
                'planned_start': str(pkg.planned_start) if pkg.planned_start else '',
                'planned_end': str(pkg.planned_end) if pkg.planned_end else '',
                'mosque_count': len(mosques),
                'avg_kpi': round(avg_kpi, 1),
                'avg_time': round(avg_time, 1),
                'delayed_count': delayed,
                'expected_pct': expected_pct,
                'deviation': round(avg_time - expected_pct, 1),
                'is_current': is_current,
                'is_past': is_past,
                'is_future': is_future,
                'mosques': [{
                    'id': m.id,
                    'code': m.code,
                    'name': m.name,
                    'overall_kpi': round(m.overall_kpi, 1),
                    'state': m.state,
                    'days_delay': m.days_delay,
                    'kpi_color': ('green' if m.overall_kpi >= 70 else
                                  'yellow' if m.overall_kpi >= 50 else
                                  'red' if m.overall_kpi > 0 else 'gray'),
                } for m in mosques],
            })
        return _json(result)

    # ══════════════════════════════════════════════════════
    # MOSQUE DETAIL (Full)
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/mosque/<int:mosque_id>', type='http', auth='user', csrf=False)
    def api_mosque_detail(self, mosque_id, **kw):
        m = request.env['mosque.mosque'].sudo().browse(mosque_id)
        if not m.exists():
            return _json({'error': 'not found'})

        # BOQ by category
        boq_cats = {}
        for boq in m.boq_ids:
            cat = boq.category_id.name if boq.category_id else 'أخرى'
            if cat not in boq_cats:
                boq_cats[cat] = {'contracted': 0, 'executed': 0, 'boq_lines': []}
            boq_cats[cat]['contracted'] += boq.contracted_qty * boq.unit_price
            boq_cats[cat]['executed'] += boq.executed_qty * boq.unit_price
            boq_cats[cat]['boq_lines'].append({
                'code': boq.item_code or '',
                'description': boq.description or '',
                'unit': boq.uom,
                'contracted_qty': boq.contracted_qty,
                'executed_qty': boq.executed_qty,
                'unit_price': boq.unit_price,
            })

        # Tasks
        tasks = []
        if m.project_id:
            for t in request.env['project.task'].sudo().search([
                ('project_id', '=', m.project_id.id),
                ('parent_id', '=', False),
            ], order='sequence'):
                subtasks = []
                for s in t.child_ids:
                    photos = []
                    for att in request.env['ir.attachment'].sudo().search([
                        ('res_model', '=', 'project.task'),
                        ('res_id', '=', s.id),
                        ('mimetype', 'like', 'image'),
                    ]):
                        n = (att.name or '').lower()
                        is_360 = ('360' in n or 'pano' in n or
                                  'equirect' in n or 'insta360' in n or
                                  n.endswith(('.insp', '.insv')))
                        photos.append({'id': att.id, 'name': att.name,
                                       'url': '/web/image/%d' % att.id,
                                       'is_360': is_360})
                    docs = []
                    for att in request.env['ir.attachment'].sudo().search([
                        ('res_model', '=', 'project.task'),
                        ('res_id', '=', s.id),
                        ('mimetype', 'not like', 'image'),
                    ]):
                        docs.append({'id': att.id, 'name': att.name,
                                     'mimetype': att.mimetype,
                                     'url': '/web/content/%d' % att.id})
                    subtasks.append({
                        'id': s.id,
                        'name': s.name,
                        'review_state': s.review_state,
                        'kanban_color': s.kanban_color,
                        'stage': s.stage_id.name if s.stage_id else '',
                        'rejection_note': s.rejection_note or '',
                        'photos': photos,
                        'docs': docs,
                    })
                tasks.append({
                    'id': t.id,
                    'name': t.name,
                    'review_state': t.review_state,
                    'kanban_color': t.kanban_color,
                    'stage': t.stage_id.name if t.stage_id else '',
                    'deadline': str(t.date_deadline) if t.date_deadline else '',
                    'approved_count': t.approved_subtask_count,
                    'pending_count': t.pending_subtask_count,
                    'rejected_count': t.rejected_subtask_count,
                    'subtask_count': len(t.child_ids),
                    'subtasks': subtasks,
                    'blocking_co': t.blocking_co_id.name if t.blocking_co_id else '',
                    'subtasks_all_green': t.subtasks_all_green,
                })

        # Certificates
        certs = []
        for c in request.env['mosque.certificate'].sudo().search(
                [('mosque_id', '=', mosque_id)], order='cert_number desc'):
            lines = []
            for line in c.line_ids:
                lines.append({
                    'boq_code': line.boq_id.item_code if line.boq_id else '',
                    'desc': (line.boq_id.description[:40]
                             if line.boq_id else ''),
                    'qty': line.this_period_qty,
                    'value': (line.this_period_qty * (line.boq_id.unit_price or 0)
                              if line.boq_id else 0),
                })
            certs.append({
                'id': c.id,
                'number': c.cert_number,
                'state': c.state,
                'period_from': str(c.period_from) if c.period_from else '',
                'period_to': str(c.period_to) if c.period_to else '',
                'total_value': c.certified_amount,
                'net_value': c.net_payable,
                'lines': lines,
            })

        # Change Orders
        cos = []
        for co in request.env['mosque.change.order'].sudo().search(
                [('mosque_id', '=', mosque_id)], order='id desc'):
            cos.append({
                'id': co.id,
                'name': co.name,
                'type': co.type,
                'reason': co.reason,
                'amount': co.amount,
                'days_extension': co.days_extension,
                'state': co.state,
            })

        # Visit reports with photos
        visits = []
        for sup in request.env['mosque.supervision'].sudo().search(
                [('mosque_id', '=', mosque_id)],
                order='report_date desc', limit=10):
            photos = []
            for att in request.env['ir.attachment'].sudo().search([
                ('res_model', '=', 'mosque.supervision'),
                ('res_id', '=', sup.id),
                ('mimetype', 'like', 'image'),
            ]):
                n = (att.name or '').lower()
                is_360 = ('360' in n or 'pano' in n or 'equirect' in n or
                          'insta360' in n or n.endswith(('.insp', '.insv')))
                photos.append({'id': att.id, 'name': att.name,
                               'url': '/web/image/%d' % att.id,
                               'is_360': is_360})
            visits.append({
                'id': sup.id,
                'date': str(sup.report_date) if sup.report_date else '',
                'engineer': sup.engineer_id.name if sup.engineer_id else '',
                'type': sup.report_type,
                'workers': sup.workers_on_site,
                'ncr': sup.ncr_count,
                'state': sup.state,
                'activities': sup.activities_done or '',
                'issues': sup.issues or '',
                'photo_count': len(sup.photo_ids),
                'photos': photos,
                'photo_360_url': sup.photo_360_url or '',
                'gps_validated': sup.gps_validated,
            })

        # Attendance
        today = date.today()
        since = datetime.combine(today - timedelta(days=30), datetime.min.time())
        attendance = []
        for att in request.env['mosque.attendance'].sudo().search([
            ('mosque_id', '=', mosque_id),
            ('check_in', '>=', since),
        ], order='check_in desc', limit=30):
            attendance.append({
                'id': att.id,
                'engineer': att.engineer_id.name if att.engineer_id else '',
                'check_in': fmt_riyadh(att.check_in, '%Y-%m-%d %H:%M'),
                'check_out': fmt_riyadh(att.check_out, '%H:%M') or None,
                'duration': att.duration,
                'validated': att.is_validated,
            })

        # AI snapshot for this mosque
        ai_data = {}
        if 'waqf.ai.mosque.snapshot' in request.env:
            Snap = request.env['waqf.ai.mosque.snapshot'].sudo()
            Alert = request.env['waqf.ai.alert'].sudo() if 'waqf.ai.alert' in request.env else False
            Pred = request.env['waqf.ai.prediction'].sudo() if 'waqf.ai.prediction' in request.env else False

            snap = Snap.search([('mosque_id', '=', mosque_id)], order='id desc', limit=1)

            if snap:
                latest_alert = Alert.search([
                    ('mosque_id', '=', mosque_id),
                    ('active', '=', True),
                    ('status', 'in', ['new', 'acknowledged', 'in_progress']),
                ], order='priority_score desc, create_date desc', limit=1) if Alert else False

                latest_prediction = Pred.search([
                    ('mosque_id', '=', mosque_id),
                ], order='create_date desc', limit=1) if Pred else False

                severity = latest_alert.severity if latest_alert else (
                    'critical' if snap.overall_kpi and snap.overall_kpi < 40 else
                    'high' if snap.overall_kpi and snap.overall_kpi < 55 else
                    'medium' if snap.overall_kpi and snap.overall_kpi < 70 else
                    'low'
                )

                ai_data = {
                    'risk_level': severity,
                    'risk_impact': latest_alert.impact_score if latest_alert else max(0, min(100, 100 - (
                            snap.overall_kpi or 0))),
                    'risk_probability': latest_alert.probability_score if latest_alert else max(0, min(100, (
                            snap.days_delay or 0) * 2 + abs(
                        (snap.financial_progress or 0) - (snap.time_progress or 0)))),
                    'health_score': round(snap.overall_kpi or 0, 1),
                    'forecast_finish': '',
                    'variance_days': latest_prediction.expected_delay_days if latest_prediction else (
                            snap.days_delay or 0),
                    'confidence_pct': round((latest_alert.confidence or latest_prediction.confidence or 0) * 100,
                                            1) if (latest_alert or latest_prediction) else 0,
                }

        perf = mosque_perf(m)
        return _json({
            'mosque': {
                'id': m.id,
                'code': m.code,
                'name': m.name,
                'city': m.city,
                'district': m.district or '',
                'state': m.state,
                'overall_kpi': round(m.overall_kpi, 1),
                'financial_kpi': round(m.financial_progress, 1),
                'time_kpi': perf['planned_pct'],
                'visit_compliance': round(m.visit_compliance, 1),
                'days_delay': perf['days_delay'],
                'status': perf['status'],
                'executed_value': perf['executed_value'],
                'contract_value': m.contract_value,
                'planned_start': str(m.planned_start) if m.planned_start else '',
                'planned_end': str(m.planned_end) if m.planned_end else '',
                'contractor': m.contractor or '',
            },
            'ai': ai_data,
            'boq_categories': [{'name': k, **v} for k, v in boq_cats.items()],
            'tasks': tasks,
            'certs': certs,
            'change_orders': cos,
            'visits': visits,
            'attendance': attendance,
        })

    # ══════════════════════════════════════════════════════
    # ON-SITE CONSULTANTS
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/onsite', type='http', auth='user', csrf=False)
    def api_onsite(self, **kw):
        """Consultants currently checked in — times in Riyadh (UTC+3)."""
        return _json(onsite_list(request.env))

    # ══════════════════════════════════════════════════════
    # LIVE STREAM
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/stream', type='http', auth='user', csrf=False)
    def api_stream(self, **kw):
        if 'waqf.live.stream' in request.env:
            stream = request.env['waqf.live.stream'].sudo().get_active_stream()
            return _json(stream or {})
        # Fallback: check config param
        url = request.env['ir.config_parameter'].sudo().get_param(
            'waqf.dashboard.live_stream_url', '')
        return _json({'url': url} if url else {})

    # ══════════════════════════════════════════════════════
    # CERT & CO ACTIONS
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/cert/<int:cert_id>/approve',
                type='json', auth='user', methods=['POST'])
    def approve_cert(self, cert_id, **kw):
        cert = request.env['mosque.certificate'].sudo().browse(cert_id)
        if cert.exists():
            cert.action_waqf_approve()
            return {'ok': True, 'state': cert.state}
        return {'ok': False}

    @http.route('/dashboard/api/cert/<int:cert_id>/reject',
                type='json', auth='user', methods=['POST'])
    def reject_cert(self, cert_id, reason='', **kw):
        cert = request.env['mosque.certificate'].sudo().browse(cert_id)
        if cert.exists():
            cert.action_reject(reason)
            return {'ok': True, 'state': cert.state}
        return {'ok': False}

    @http.route('/dashboard/api/co/<int:co_id>/approve',
                type='json', auth='user', methods=['POST'])
    def approve_co(self, co_id, **kw):
        co = request.env['mosque.change.order'].sudo().browse(co_id)
        if co.exists():
            co.action_approve()
            return {'ok': True, 'state': co.state}
        return {'ok': False}

    @http.route('/dashboard/api/co/<int:co_id>/reject',
                type='json', auth='user', methods=['POST'])
    def reject_co(self, co_id, **kw):
        co = request.env['mosque.change.order'].sudo().browse(co_id)
        if co.exists():
            co.action_reject()
            return {'ok': True, 'state': co.state}
        return {'ok': False}
