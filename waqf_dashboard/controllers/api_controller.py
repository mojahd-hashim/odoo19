import json
from odoo import http
from odoo.http import request
from datetime import date, datetime, timedelta


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
        Mosque = request.env['mosque.mosque'].sudo()
        Cert = request.env['mosque.certificate'].sudo()
        CO = request.env['mosque.change.order'].sudo()

        mosques = Mosque.search([('is_demo', '=', False)])
        total_value = sum(mosques.mapped('total_boq_value'))
        avg_kpi = sum(mosques.mapped('overall_kpi')) / len(mosques) if mosques else 0
        delayed = mosques.filtered(lambda m: m.days_delay > 0)
        critical = mosques.filtered(lambda m: m.overall_kpi < 50 and m.overall_kpi > 0)

        # Pending certs & COs
        pending_certs = Cert.search_count(
            [('state', 'in', ['submitted', 'consultant_approved'])])
        pending_cos = CO.search_count([('state', '=', 'review')])
        co_value = sum(CO.search([('state', 'not in', ['rejected'])]).mapped('amount'))

        # Total delay days
        total_delay = sum(delayed.mapped('days_delay'))

        # On-time mosques
        on_time = len(mosques) - len(delayed)

        # Financial progress avg
        avg_financial = (sum(mosques.mapped('financial_progress')) / len(mosques)
                         if mosques else 0)

        # Compare vs last week — from AI snapshots if available
        prev_avg_kpi = avg_kpi
        prev_critical = len(critical)
        prev_pending = pending_certs
        has_ai = 'waqf.ai.snapshot.run' in request.env

        if has_ai:
            Snap = request.env['waqf.ai.mosque.snapshot'].sudo()
            Alert = request.env['waqf.ai.alert'].sudo() if 'waqf.ai.alert' in request.env else False

            latest_run = request.env['waqf.ai.snapshot.run'].sudo().search(
                [('status', 'in', ['done', 'done_with_ai_error'])],
                order='run_datetime desc',
                limit=1
            )

            domain = [('run_id', '=', latest_run.id)] if latest_run else []

            for s in Snap.search(domain):
                latest_alert = Alert.search([
                    ('mosque_id', '=', s.mosque_id.id),
                    ('active', '=', True),
                    ('status', 'in', ['new', 'acknowledged', 'in_progress']),
                ], order='priority_score desc, create_date desc', limit=1) if Alert else False

                impact = latest_alert.impact_score if latest_alert else max(
                    0,
                    min(100, 100 - (s.overall_kpi or 0))
                )

                probability = latest_alert.probability_score if latest_alert else max(
                    0,
                    min(100, (s.days_delay or 0) * 2 + abs((s.financial_progress or 0) - (s.time_progress or 0)))
                )

                risk_level = latest_alert.severity if latest_alert else (
                    'critical' if impact >= 75 and probability >= 60 else
                    'high' if impact >= 60 or probability >= 60 else
                    'medium' if impact >= 35 or probability >= 35 else
                    'low'
                )

                points.append({
                    'mosque_id': s.mosque_id.id,
                    'mosque_name': s.mosque_id.name,
                    'mosque_code': s.mosque_id.code,
                    'impact': round(impact, 1),
                    'probability': round(probability, 1),
                    'size': s.contract_value or s.mosque_id.contract_value,
                    'kpi': round(s.overall_kpi or 0, 1),
                    'risk_level': risk_level,
                })

        return _json({
            'total_contract_value': total_value,
            'avg_kpi': round(avg_kpi, 1),
            'avg_kpi_delta': round(avg_kpi - prev_avg_kpi, 1),
            'delayed_count': len(delayed),
            'critical_count': len(critical),
            'critical_delta': len(critical) - prev_critical,
            'total_delay_days': total_delay,
            'pending_certs': pending_certs,
            'pending_certs_delta': pending_certs - prev_pending,
            'pending_cos': pending_cos,
            'co_value': co_value,
            'on_time_count': on_time,
            'mosque_count': len(mosques),
            'avg_financial': round(avg_financial, 1),
        })

    # ══════════════════════════════════════════════════════
    # SMART ALERTS — from AI Risk Center
    # ══════════════════════════════════════════════════════
    @http.route('/dashboard/api/alerts', type='http', auth='user', csrf=False)
    def api_alerts(self, severity=None, category=None, **kw):
        """
        Primary source: waqf.ai.alert (AI Risk Center)
        Fallback: compute alerts from raw data if AI module absent
        """
        has_ai = 'waqf.ai.alert' in request.env
        alerts = []

        if has_ai:
            Alert = request.env['waqf.ai.alert'].sudo()
            domain = [('status', 'in', ['new', 'acknowledged'])]
            if severity:
                domain.append(('severity', '=', severity))
            if category:
                domain.append(('category', '=', category))

            # استبدله بهذا
            sev_map = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
            alerts_raw = Alert.search(domain, order='priority_score desc, create_date desc', limit=25)
            alerts_raw = sorted(alerts_raw, key=lambda a: sev_map.get(a.severity, 9))
            for a in alerts_raw:
                alerts.append({
                    'id': a.id,
                    'title': a.title,
                    'description': a.summary or '',
                    'severity': a.severity,
                    'category': a.alert_type,
                    'mosque_id': a.mosque_id.id if a.mosque_id else None,
                    'mosque_name': a.mosque_id.name if a.mosque_id else '',
                    'mosque_code': a.mosque_id.code if a.mosque_id else '',
                    'cta_label': 'عرض التفاصيل',
                    'state': a.status,
                    'created_at': str(a.create_date),
                })
        else:
            # ── Fallback: compute from raw data ──────────────
            Mosque = request.env['mosque.mosque'].sudo()
            Cert = request.env['mosque.certificate'].sudo()
            CO = request.env['mosque.change.order'].sudo()

            # Critical mosques
            for m in Mosque.search([('overall_kpi', '<', 45), ('overall_kpi', '>', 0),
                                    ('is_demo', '=', False)]):
                alerts.append({
                    'id': m.id, 'severity': 'critical', 'category': 'delay',
                    'title': f'{m.name} — KPI حرج {round(m.overall_kpi)}%',
                    'description': f'تأخير {m.days_delay} يوم · يحتاج تدخل فوري',
                    'mosque_id': m.id, 'mosque_name': m.name, 'mosque_code': m.code,
                    'cta_label': 'فتح المسجد', 'state': 'new', 'created_at': '',
                })

            # Pending certs > 7 days
            cutoff = datetime.now() - timedelta(days=7)
            for c in Cert.search([('state', 'in', ['submitted', 'consultant_approved']),
                                  ('create_date', '<', cutoff)]):
                alerts.append({
                    'id': 10000 + c.id, 'severity': 'high', 'category': 'financial',
                    'title': f'مستخلص #{c.cert_number} معلق منذ أكثر من 7 أيام',
                    'description': f'{c.mosque_id.name} · {round(c.certified_amount or 0):,} ريال',
                    'mosque_id': c.mosque_id.id if c.mosque_id else None,
                    'mosque_name': c.mosque_id.name if c.mosque_id else '',
                    'mosque_code': c.mosque_id.code if c.mosque_id else '',
                    'cta_label': 'مراجعة', 'state': 'new', 'created_at': '',
                })

            # High value COs pending
            for co in CO.search([('state', '=', 'review'), ('amount', '>', 100000)]):
                alerts.append({
                    'id': 20000 + co.id, 'severity': 'high', 'category': 'financial',
                    'title': f'أمر تغيير {co.name} بقيمة عالية — {round(co.amount):,} ريال',
                    'description': f'{co.mosque_id.name} · {co.reason or ""}',
                    'mosque_id': co.mosque_id.id if co.mosque_id else None,
                    'mosque_name': co.mosque_id.name if co.mosque_id else '',
                    'mosque_code': co.mosque_id.code if co.mosque_id else '',
                    'cta_label': 'اعتماد', 'state': 'new', 'created_at': '',
                })

            # Sort by severity
            sev_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
            alerts.sort(key=lambda a: sev_order.get(a['severity'], 9))
            alerts = alerts[:20]

        return _json({
            'alerts': alerts,
            'total': len(alerts),
            'source': 'ai_center' if has_ai else 'computed',
        })

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
        mosques = request.env['mosque.mosque'].sudo().search(
            [('is_demo', '=', False)], order='code')
        result = []
        for m in mosques:
            result.append({
                'id': m.id,
                'code': m.code,
                'name': m.name,
                'city': m.city,
                'district': m.district or '',
                'state': m.state,
                'package': m.package_id.name if m.package_id else '',
                'package_id': m.package_id.id if m.package_id else 0,
                'overall_kpi': round(m.overall_kpi, 1),
                'financial_pct': round(m.financial_progress, 1),
                'time_pct': round(m.time_progress, 1),
                'days_delay': m.days_delay,
                'contract_value': m.contract_value,
                'planned_start': str(m.planned_start) if m.planned_start else '',
                'planned_end': str(m.planned_end) if m.planned_end else '',
                'lat': m.latitude,
                'lng': m.longitude,
                'kpi_color': ('green' if m.overall_kpi >= 70 else
                              'yellow' if m.overall_kpi >= 50 else
                              'red' if m.overall_kpi > 0 else 'gray'),
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
                'check_in': str(att.check_in.strftime('%Y-%m-%d %H:%M')) if att.check_in else '',
                'check_out': str(att.check_out.strftime('%H:%M')) if att.check_out else None,
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
                'time_kpi': round(m.time_progress, 1),
                'visit_compliance': round(m.visit_compliance, 1),
                'days_delay': m.days_delay,
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
        today_start = datetime.combine(date.today(), datetime.min.time())
        result = []
        for a in request.env['mosque.attendance'].sudo().search([
            ('check_in', '>=', today_start),
            ('check_out', '=', False),
        ]):
            elapsed = ((datetime.now() - a.check_in).total_seconds() / 3600
                       if a.check_in else 0)
            result.append({
                'name': a.engineer_id.name if a.engineer_id else '',
                'mosque': a.mosque_id.name if a.mosque_id else '',
                'code': a.mosque_id.code if a.mosque_id else '',
                'checkin': a.check_in.strftime('%H:%M') if a.check_in else '',
                'elapsed': round(elapsed, 1),
                'validated': a.is_validated,
            })
        return _json(result)

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
