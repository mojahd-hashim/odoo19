import json
from odoo import http
from odoo.http import request
from datetime import date, datetime, timedelta


def _json(data):
    return request.make_response(
        json.dumps(data, ensure_ascii=False, default=str),
        headers=[('Content-Type', 'application/json')])


class WaqfDashboardAPI(http.Controller):

    # ── Summary KPIs ──────────────────────────────────────────
    @http.route('/dashboard/api/summary', type='http', auth='user', csrf=False)
    def api_summary(self, **kw):
        Mosque = request.env['mosque.mosque'].sudo()
        Cert   = request.env['mosque.certificate'].sudo()
        CO     = request.env['mosque.change.order'].sudo()

        mosques      = Mosque.search([('is_demo', '=', False)])
        total_value  = sum(mosques.mapped('contract_value'))
        avg_kpi      = sum(mosques.mapped('overall_kpi')) / len(mosques) if mosques else 0
        delayed      = len(mosques.filtered(lambda m: m.days_delay > 0))
        pending_cert = Cert.search_count([('state', 'in', ['submitted', 'consultant_approved'])])
        pending_co   = CO.search_count([('state', '=', 'review')])

        # Financial
        total_executed = sum(mosques.mapped('financial_progress')) / len(mosques) if mosques else 0

        return _json({
            'total_contract_value': total_value,
            'avg_kpi':              round(avg_kpi, 1),
            'delayed_mosques':      delayed,
            'pending_certs':        pending_cert,
            'pending_cos':          pending_co,
            'financial_pct':        round(total_executed, 1),
            'mosque_count':         len(mosques),
        })

    # ── Mosque List with KPIs ─────────────────────────────────
    @http.route('/dashboard/api/mosques', type='http', auth='user', csrf=False)
    def api_mosques(self, **kw):
        mosques = request.env['mosque.mosque'].sudo().search(
            [('is_demo', '=', False)], order='code')
        result = []
        for m in mosques:
            result.append({
                'id':           m.id,
                'code':         m.code,
                'name':         m.name,
                'city':         m.city,
                'district':     m.district or '',
                'state':        m.state,
                'package':      m.package_id.name if m.package_id else '',
                'package_id':   m.package_id.id if m.package_id else 0,
                'overall_kpi':  round(m.overall_kpi, 1),
                'financial_pct':round(m.financial_progress, 1),
                'time_pct':     round(m.time_progress, 1),
                'days_delay':   m.days_delay,
                'contract_value': m.contract_value,
                'planned_start':  str(m.planned_start) if m.planned_start else '',
                'planned_end':    str(m.planned_end) if m.planned_end else '',
                'lat':          m.latitude,
                'lng':          m.longitude,
                'kpi_color': (
                    'green'  if m.overall_kpi >= 70 else
                    'yellow' if m.overall_kpi >= 50 else
                    'red'    if m.overall_kpi > 0  else 'gray'
                ),
            })
        return _json(result)

    # ── Packages (Gantt) ──────────────────────────────────────
    @http.route('/dashboard/api/packages', type='http', auth='user', csrf=False)
    def api_packages(self, **kw):
        packages = request.env['mosque.package'].sudo().search([], order='sequence')
        today = date.today()
        result = []
        for pkg in packages:
            mosques     = pkg.mosque_ids.filtered(lambda m: not m.is_demo)
            avg_kpi     = sum(mosques.mapped('overall_kpi')) / len(mosques) if mosques else 0
            avg_fin     = sum(mosques.mapped('financial_progress')) / len(mosques) if mosques else 0
            avg_time    = sum(mosques.mapped('time_progress')) / len(mosques) if mosques else 0
            delayed     = len(mosques.filtered(lambda m: m.days_delay > 0))

            # Deviation
            if pkg.planned_end and pkg.planned_start:
                total_days = (pkg.planned_end - pkg.planned_start).days
                elapsed    = (today - pkg.planned_start).days
                expected_pct = min(100, round(elapsed / total_days * 100, 1)) if total_days > 0 else 0
            else:
                expected_pct = 0

            result.append({
                'id':           pkg.id,
                'code':         pkg.code,
                'name':         pkg.name,
                'planned_start':str(pkg.planned_start) if pkg.planned_start else '',
                'planned_end':  str(pkg.planned_end)   if pkg.planned_end   else '',
                'mosque_count': len(mosques),
                'avg_kpi':      round(avg_kpi, 1),
                'avg_financial':round(avg_fin, 1),
                'avg_time':     round(avg_time, 1),
                'delayed_count':delayed,
                'expected_pct': expected_pct,
                'deviation':    round(avg_time - expected_pct, 1),
                'mosques': [{
                    'id': m.id, 'code': m.code, 'name': m.name,
                    'overall_kpi': round(m.overall_kpi, 1),
                    'state': m.state,
                } for m in mosques],
            })
        return _json(result)

    # ── Mosque Detail ─────────────────────────────────────────
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
                boq_cats[cat] = {'contracted': 0, 'executed': 0, 'approved': 0}
            boq_cats[cat]['contracted'] += boq.contracted_qty * boq.unit_price
            boq_cats[cat]['executed']   += boq.executed_qty   * boq.unit_price

        # Tasks
        tasks = []
        if m.project_id:
            for t in request.env['project.task'].sudo().search([
                ('project_id', '=', m.project_id.id),
                ('parent_id',  '=', False),
            ], order='sequence'):
                # Photos from subtasks
                subtasks = []
                for s in t.child_ids:
                    photo_ids = []
                    for att in request.env['ir.attachment'].sudo().search([
                        ('res_model', '=', 'project.task'),
                        ('res_id',    '=', s.id),
                        ('mimetype',  'like', 'image'),
                    ]):
                        photo_ids.append({
                            'id':   att.id,
                            'name': att.name,
                            'url':  '/web/image/%d' % att.id,
                        })

                    # Docs
                    doc_ids = []
                    for att in request.env['ir.attachment'].sudo().search([
                        ('res_model', '=', 'project.task'),
                        ('res_id',    '=', s.id),
                        ('mimetype',  'not like', 'image'),
                    ]):
                        doc_ids.append({
                            'id':       att.id,
                            'name':     att.name,
                            'mimetype': att.mimetype,
                            'url':      '/web/content/%d' % att.id,
                        })

                    subtasks.append({
                        'id':           s.id,
                        'name':         s.name,
                        'review_state': s.review_state,
                        'kanban_color': s.kanban_color,
                        'stage':        s.stage_id.name if s.stage_id else '',
                        'rejection_note': s.rejection_note or '',
                        'photos':       photo_ids,
                        'docs':         doc_ids,
                    })

                tasks.append({
                    'id':            t.id,
                    'name':          t.name,
                    'review_state':  t.review_state,
                    'kanban_color':  t.kanban_color,
                    'stage':         t.stage_id.name if t.stage_id else '',
                    'waqf_stage':    t.stage_id.waqf_stage if t.stage_id else '',
                    'deadline':      str(t.date_deadline) if t.date_deadline else '',
                    'subtasks_all_green': t.subtasks_all_green,
                    'approved_count': t.approved_subtask_count,
                    'pending_count':  t.pending_subtask_count,
                    'rejected_count': t.rejected_subtask_count,
                    'subtask_count':  len(t.child_ids),
                    'subtasks':       subtasks,
                    'blocking_co':    t.blocking_co_id.name if t.blocking_co_id else '',
                })

        # Certificates
        certs = []
        for c in request.env['mosque.certificate'].sudo().search([
            ('mosque_id', '=', mosque_id)], order='cert_number desc'):
            lines = []
            for line in c.line_ids:
                lines.append({
                    'boq_code':  line.boq_id.item_code if line.boq_id else '',
                    'desc':      line.boq_id.description[:40] if line.boq_id else '',
                    'qty':       line.this_period_qty,
                    'value':     line.this_period_qty * (line.boq_id.unit_price or 0)
                                 if line.boq_id else 0,
                })
            certs.append({
                'id':           c.id,
                'number':       c.cert_number,
                'state':        c.state,
                'period_from':  str(c.period_from) if c.period_from else '',
                'period_to':    str(c.period_to)   if c.period_to   else '',
                'total_value':  c.certified_amount,
                'net_value':    c.net_payable,
                'lines':        lines,
            })

        # Change Orders
        cos = []
        for co in request.env['mosque.change.order'].sudo().search([
            ('mosque_id', '=', mosque_id)], order='id desc'):
            cos.append({
                'id':            co.id,
                'name':          co.name,
                'type':          co.type,
                'reason':        co.reason,
                'amount':        co.amount,
                'days_extension':co.days_extension,
                'state':         co.state,
            })

            # Visit reports
            visits = []
            for sup in request.env['mosque.supervision'].sudo().search([
                ('mosque_id', '=', mosque_id)], order='report_date desc', limit=10):

                # Photos with 360 detection
                photos = []
                for att in request.env['ir.attachment'].sudo().search([
                    ('res_model', '=', 'mosque.supervision'),
                    ('res_id', '=', sup.id),
                    ('mimetype', 'like', 'image'),
                ]):
                    name_lower = (att.name or '').lower()
                    is_360 = (
                            '360' in name_lower or
                            'pano' in name_lower or
                            'equirect' in name_lower or
                            'insta360' in name_lower or
                            name_lower.endswith(('.insp', '.insv'))
                    )
                    photos.append({
                        'id': att.id,
                        'name': att.name or '',
                        'url': '/web/image/%d' % att.id,
                        'is_360': is_360,
                    })

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
                    'photos': photos,  # ← أُضيف
                })

        # Attendance history
        today = date.today()
        since = datetime.combine(today - timedelta(days=30), datetime.min.time())
        attendance = []
        for att in request.env['mosque.attendance'].sudo().search([
            ('mosque_id', '=', mosque_id),
            ('check_in',  '>=', since),
        ], order='check_in desc', limit=30):
            attendance.append({
                'id':        att.id,
                'engineer':  att.engineer_id.name if att.engineer_id else '',
                'check_in':  str(att.check_in.strftime('%Y-%m-%d %H:%M')) if att.check_in else '',
                'check_out': str(att.check_out.strftime('%H:%M')) if att.check_out else None,
                'duration':  att.duration,
                'validated': att.is_validated,
            })

        return _json({
            'mosque': {
                'id':             m.id,
                'code':           m.code,
                'name':           m.name,
                'city':           m.city,
                'district':       m.district or '',
                'state':          m.state,
                'overall_kpi':    round(m.overall_kpi, 1),
                'financial_kpi':  round(m.financial_progress, 1),
                'time_kpi':       round(m.time_progress, 1),
                'visit_compliance':round(m.visit_compliance, 1),
                'days_delay':     m.days_delay,
                'contract_value': m.contract_value,
                'planned_start':  str(m.planned_start) if m.planned_start else '',
                'planned_end':    str(m.planned_end)   if m.planned_end   else '',
                'contractor':     m.contractor or '',
            },
            'boq_categories': [
                {'name': k, **v} for k, v in boq_cats.items()
            ],
            'tasks':      tasks,
            'certs':      certs,
            'change_orders': cos,
            'visits':     visits,
            'attendance': attendance,
        })

    # ── Approve / Reject Certificate ──────────────────────────
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

    # ── Approve / Reject Change Order ─────────────────────────
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

    # ── On-site consultants ───────────────────────────────────
    @http.route('/dashboard/api/onsite', type='http', auth='user', csrf=False)
    def api_onsite(self, **kw):
        today_start = datetime.combine(date.today(), datetime.min.time())
        att = request.env['mosque.attendance'].sudo().search([
            ('check_in',  '>=', today_start),
            ('check_out', '=',  False),
        ])
        result = []
        for a in att:
            elapsed = (datetime.now() - a.check_in).total_seconds() / 3600 if a.check_in else 0
            result.append({
                'name':     a.engineer_id.name if a.engineer_id else '',
                'mosque':   a.mosque_id.name   if a.mosque_id   else '',
                'code':     a.mosque_id.code   if a.mosque_id   else '',
                'checkin':  str(a.check_in.strftime('%H:%M')) if a.check_in else '',
                'elapsed':  round(elapsed, 1),
                'validated':a.is_validated,
            })
        return _json(result)

    # ── Live stream ───────────────────────────────────────────
    @http.route('/dashboard/api/stream', type='http', auth='user', csrf=False)
    def api_stream(self, **kw):
        stream = request.env['waqf.live.stream'].sudo().get_active_stream()
        return _json(stream or {})

    @http.route('/dashboard/api/stream/start', type='json', auth='user', methods=['POST'])
    def start_stream(self, mosque_id=None, url='', label='', **kw):
        stream = request.env['waqf.live.stream'].sudo().create({
            'name':       label or 'بث مباشر',
            'mosque_id':  mosque_id,
            'stream_url': url,
            'is_active':  True,
        })
        request.env['ir.config_parameter'].sudo().set_param(
            'waqf.dashboard.live_stream_url', url)
        return {'ok': True, 'id': stream.id}

    @http.route('/dashboard/api/stream/end', type='json', auth='user', methods=['POST'])
    def end_stream(self, stream_id=None, **kw):
        if stream_id:
            stream = request.env['waqf.live.stream'].sudo().browse(stream_id)
            stream.action_end_stream()
        return {'ok': True}