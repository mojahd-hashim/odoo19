from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError, UserError
from datetime import date, timedelta
import base64
import json
# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError
from datetime import date
import base64


class ContractorPortal(http.Controller):

    def _get_portal_user(self):
        """يرجع waqf.portal.user للمستخدم الحالي إذا كان مقاولاً."""
        contractor_roles = ['site_supervisor', 'contractor_admin', 'contractor_engineer']
        portal_user = request.env['waqf.portal.user'].sudo().search([
            ('user_id', '=', request.env.user.id),
            ('role', 'in', contractor_roles),
            ('is_active', '=', True),
        ], limit=1)
        return portal_user or None

    def _get_supervisor(self):
        """Get current logged-in supervisor — يدعم النظام القديم والجديد."""
        # ① النظام الجديد — waqf.portal.user
        portal_user = self._get_portal_user()
        if portal_user:
            return portal_user.user_id.partner_id

        # ② النظام القديم — contractor_supervisor
        partner = request.env.user.partner_id
        if not partner.contractor_supervisor:
            return None
        return partner

    def _check_mosque_access(self, mosque_id):
        """Verify supervisor has granted BOQ access to this mosque."""
        supervisor = self._get_supervisor()
        if not supervisor:
            return False
        Access = request.env['contractor.boq.access'].sudo()
        return Access.check_contractor_access(mosque_id, supervisor.id)

        # ══════════════════════════════════════════════════════════════
        # استبدل portal_home كاملاً
        # ══════════════════════════════════════════════════════════════

    @http.route('/contractor', type='http', auth='user', website=True)
    def portal_home(self, **kwargs):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()

        if not portal_user and not supervisor:
            return request.redirect('/web')

        if portal_user:
            mosques = portal_user.effective_mosque_ids.sorted('name')
            is_admin = portal_user.role == 'contractor_admin'
        else:
            mosque = supervisor.assigned_mosque_id
            if mosque:
                return request.redirect(f'/contractor/mosque/{mosque.id}')
            return request.render('waqf_contractor_portal.tmpl_no_mosque', {})

        if len(mosques) == 1:
            return request.redirect(f'/contractor/mosque/{mosques[0].id}')

        # ── إحصاءات سريعة لكل المساجد ────────────────────────
        mosque_ids = mosques.ids

        # أوامر عمل
        wo_pending = request.env['contractor.work.order'].sudo().search_count([
            ('mosque_id', 'in', mosque_ids), ('state', '=', 'submitted')])
        wo_rework = request.env['contractor.work.order'].sudo().search_count([
            ('mosque_id', 'in', mosque_ids), ('state', '=', 'rework')])
        wo_active = request.env['contractor.work.order'].sudo().search_count([
            ('mosque_id', 'in', mosque_ids), ('state', '=', 'approved')])

        # عينات المواد
        sub_pending = request.env['contractor.material.submittal'].sudo().search_count([
            ('mosque_id', 'in', mosque_ids), ('state', '=', 'submitted')])
        sub_approved = request.env['contractor.material.submittal'].sudo().search_count([
            ('mosque_id', 'in', mosque_ids), ('state', '=', 'approved')])
        sub_rejected = request.env['contractor.material.submittal'].sudo().search_count([
            ('mosque_id', 'in', mosque_ids), ('state', '=', 'rejected')])

        # تأهيلات
        qual_domain = []
        if supervisor:
            qual_domain.append(('supervisor_id', '=', supervisor.id))
        qual_approved = request.env['contractor.qualification'].sudo().search_count(
            qual_domain + [('state', '=', 'approved')])
        qual_pending = request.env['contractor.qualification'].sudo().search_count(
            qual_domain + [('state', '=', 'submitted')])

        # أوامر تتطلب إجراء (rework)
        rework_orders = request.env['contractor.work.order'].sudo().search([
            ('mosque_id', 'in', mosque_ids), ('state', '=', 'rework')
        ], limit=5, order='write_date desc')

        # عينات مرفوضة تتطلب إجراء
        rejected_subs = request.env['contractor.material.submittal'].sudo().search([
            ('mosque_id', 'in', mosque_ids), ('state', '=', 'rejected')
        ], limit=5, order='write_date desc')

        return request.render('waqf_contractor_portal.tmpl_mosque_select', {
            'portal_user': portal_user,
            'mosques': mosques,
            'is_admin': is_admin,
            # إحصاءات
            'wo_pending': wo_pending,
            'wo_rework': wo_rework,
            'wo_active': wo_active,
            'sub_pending': sub_pending,
            'sub_approved': sub_approved,
            'sub_rejected': sub_rejected,
            'qual_approved': qual_approved,
            'qual_pending': qual_pending,
            # طلبات تتطلب إجراء
            'rework_orders': rework_orders,
            'rejected_subs': rejected_subs,
        })

    def _resolve_mosque(self, mosque_id):
        """تحقق أن المستخدم يملك صلاحية على المسجد."""
        portal_user = self._get_portal_user()
        mosque = request.env['mosque.mosque'].sudo().browse(mosque_id)
        if not mosque.exists():
            return None, None
        if portal_user:
            if mosque not in portal_user.effective_mosque_ids:
                return None, None
        return mosque, portal_user

    def _wo_domain(self, portal_user, supervisor, mosque_id=None):
        domain = []
        if mosque_id:
            domain.append(('mosque_id', '=', mosque_id))
        if portal_user:
            domain.append(('portal_user_id', '=', portal_user.user_id.id))
        elif supervisor:
            domain.append(('supervisor_id', '=', supervisor.id))
        return domain

    @http.route('/contractor/mosque/<int:mosque_id>', type='http', auth='user', website=True)
    def mosque_home(self, mosque_id, **kwargs):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()

        if not portal_user and not supervisor:
            return request.redirect('/web')

        mosque = request.env['mosque.mosque'].sudo().browse(mosque_id)
        if not mosque.exists():
            return request.redirect('/contractor')

        # تحقق من الصلاحية
        if portal_user:
            if mosque not in portal_user.effective_mosque_ids:
                return request.redirect('/contractor')
            has_access = bool(portal_user.permission_id[:1].can_submit_works)
        else:
            has_access = self._check_mosque_access(mosque_id)

        # ── Work Orders (الجديدة) ─────────────────────────────
        WO = request.env['contractor.work.order'].sudo()
        wo_domain = [('mosque_id', '=', mosque.id)]
        if supervisor:
            wo_domain.append(('supervisor_id', '=', supervisor.id))

        all_wo = WO.search(wo_domain, order='date_requested desc')
        recent_work_orders = all_wo[:8]

        pending_wo_count = sum(1 for w in all_wo if w.state == 'submitted')
        active_wo_count = sum(1 for w in all_wo if w.state == 'approved')
        delivered_wo_count = sum(1 for w in all_wo if w.state == 'delivered')
        total_wo_count = len(all_wo)

        rejected_work_orders = all_wo.filtered(lambda w: w.state == 'rework')

        # ── Legacy Work Logs ──────────────────────────────────
        log_domain = [('mosque_id', '=', mosque.id)]
        if supervisor:
            log_domain.append(('supervisor_id', '=', supervisor.id))

        recent_logs = request.env['contractor.work.log'].sudo().search(
            log_domain, limit=5, order='log_date desc')
        rejected_logs = request.env['contractor.work.log'].sudo().search(
            log_domain + [('state', '=', 'rejected')]) if has_access else []

        # ── Tasks ─────────────────────────────────────────────
        tasks = []
        if mosque.project_id:
            tasks = request.env['project.task'].sudo().search([
                ('project_id', '=', mosque.project_id.id),
                ('parent_id', '=', False),
                ('stage_id.fold', '=', False),
            ], order='date_deadline asc')

        # ── Submittals count ──────────────────────────────────
        active_submittals = request.env['contractor.material.submittal'].sudo().search_count([
            ('mosque_id', '=', mosque.id),
            ('state', 'in', ['draft', 'submitted']),
        ])
        qual_domain_base = []
        if supervisor:
            qual_domain_base.append(('supervisor_id', '=', supervisor.id))

        qual_approved_count = request.env['contractor.qualification'].sudo().search_count(
            qual_domain_base + [('state', '=', 'approved')])
        qual_pending_count = request.env['contractor.qualification'].sudo().search_count(
            qual_domain_base + [('state', '=', 'submitted')])

        # ── Submittals stats ───────────────────────────────────
        sub_domain_base = [('mosque_id', '=', mosque.id)]
        sub_approved_count = request.env['contractor.material.submittal'].sudo().search_count(
            sub_domain_base + [('state', '=', 'approved')])
        sub_pending_count = request.env['contractor.material.submittal'].sudo().search_count(
            sub_domain_base + [('state', '=', 'submitted')])

        return request.render('waqf_contractor_portal.tmpl_home', {
            'supervisor': supervisor,
            'portal_user': portal_user,
            'mosque': mosque,
            'has_access': has_access,
            'tasks': tasks,
            'recent_logs': recent_logs,
            'rejected_logs': rejected_logs,
            'recent_work_orders': recent_work_orders,
            'rejected_work_orders': rejected_work_orders,
            'pending_wo_count': pending_wo_count,
            'active_wo_count': active_wo_count,
            'delivered_wo_count': delivered_wo_count,
            'total_wo_count': total_wo_count,
            'active_submittals': active_submittals,
            'qual_approved_count': qual_approved_count,
            'qual_pending_count': qual_pending_count,
            'sub_approved_count': sub_approved_count,
            'sub_pending_count': sub_pending_count,
        })

    # ══════════════════════════════════════════════════════
    # QUALIFICATIONS LIST
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/qualifications', type='http',
                auth='user', website=True)
    def qualifications_list(self, state=None, **kwargs):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        domain = []
        if supervisor:
            domain.append(('supervisor_id', '=', supervisor.id))
        if state and state != 'all':
            domain.append(('state', '=', state))

        quals = request.env['contractor.qualification'].sudo().search(
            domain, order='id desc')

        counts = {
            'all': len(quals),
            'draft': sum(1 for q in quals if q.state == 'draft'),
            'submitted': sum(1 for q in quals if q.state == 'submitted'),
            'approved': sum(1 for q in quals if q.state == 'approved'),
            'rejected': sum(1 for q in quals if q.state == 'rejected'),
        }

        return request.render('waqf_contractor_portal.tmpl_qual_list', {
            'portal_user': portal_user,
            'supervisor': supervisor,
            'qualifications': quals,
            'active_state': state or 'all',
            'counts': counts,
        })

    # ══════════════════════════════════════════════════════
    # SUBMITTALS LIST
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/submittals', type='http',
                auth='user', website=True)
    def submittals_list(self, state=None, mosque=None, **kwargs):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        domain = []
        if portal_user:
            domain.append(('mosque_id', 'in',
                           portal_user.effective_mosque_ids.ids))
        elif supervisor and supervisor.assigned_mosque_id:
            domain.append(('mosque_id', '=', supervisor.assigned_mosque_id.id))

        if mosque:
            domain.append(('mosque_id', '=', int(mosque)))
        if state and state != 'all':
            domain.append(('state', '=', state))

        subs = request.env['contractor.material.submittal'].sudo().search(
            domain, order='date_submitted desc, id desc')

        counts = {
            'all': len(subs),
            'draft': sum(1 for s in subs if s.state == 'draft'),
            'submitted': sum(1 for s in subs if s.state == 'submitted'),
            'approved': sum(1 for s in subs if s.state == 'approved'),
            'rejected': sum(1 for s in subs if s.state == 'rejected'),
        }

        mosques = portal_user.effective_mosque_ids if portal_user else []

        return request.render('waqf_contractor_portal.tmpl_sub_list', {
            'portal_user': portal_user,
            'supervisor': supervisor,
            'submittals': subs,
            'active_state': state or 'all',
            'active_mosque': int(mosque) if mosque else None,
            'mosques': mosques,
            'counts': counts,
        })


    @http.route('/contractor/task/<int:task_id>', type='http',
                auth='user', website=True)
    def task_detail(self, task_id, **kwargs):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()

        if not portal_user and not supervisor:
            return request.redirect('/contractor')

        task = request.env['project.task'].sudo().browse(task_id)

        # تحديد المسجد من المهمة
        mosque = task.project_id.mosque_id if task.project_id else None
        if not mosque:
            return request.redirect('/contractor')

        # BOQ items
        boq_items = request.env['mosque.boq'].sudo().search([
            ('mosque_id', '=', mosque.id),
        ], order='category_id, sequence')

        # Work logs
        domain_logs = [('task_id', '=', task_id)]
        if supervisor:
            domain_logs.append(('supervisor_id', '=', supervisor.id))

        logs = request.env['contractor.work.log'].sudo().search(
            domain_logs, order='log_date desc')

        return request.render('waqf_contractor_portal.tmpl_task_detail', {
            'supervisor': supervisor,
            'portal_user': portal_user,
            'mosque': mosque,
            'task': task,
            'boq_items': boq_items,
            'logs': logs,
        })

    # ── Submit Work Log ───────────────────────────────────────────
    @http.route('/contractor/work/submit', type='http',
                auth='user', website=True, methods=['POST'])
    def submit_work(self, **post):
        supervisor = self._get_supervisor()
        if not supervisor:
            return request.redirect('/contractor')

        mosque = supervisor.assigned_mosque_id
        task_id = int(post.get('task_id', 0))
        boq_id = int(post.get('boq_id', 0))
        qty = float(post.get('qty_executed', 0))
        desc = post.get('name', '').strip()
        location = post.get('location_detail', '').strip()

        if not all([boq_id, qty, desc]):
            return request.redirect('/contractor/task/%d?error=missing' % task_id)

        # Check qty warning before creating
        boq = request.env['mosque.boq'].sudo().browse(boq_id)
        other_logs = request.env['contractor.work.log'].sudo().search([
            ('boq_id', '=', boq_id),
            ('state', 'in', ['submitted', 'approved']),
        ])
        total_qty = sum(other_logs.mapped('qty_executed')) + qty
        needs_co = total_qty > boq.contracted_qty * 1.10

        WorkLog = request.env['contractor.work.log'].sudo()
        log = WorkLog.create({
            'name': desc,
            'mosque_id': mosque.id,
            'supervisor_id': supervisor.id,
            'boq_id': boq_id,
            'task_id': task_id,
            'log_date': post.get('log_date'),
            'qty_executed': qty,
            'location_detail': location,
        })

        if needs_co:
            return request.redirect(
                '/contractor/change-order/new?log_id=%d' % log.id)

        return request.redirect(
            '/contractor/work/%d/photos' % log.id)

    # ── Upload Photos ─────────────────────────────────────────────
    @http.route('/contractor/work/<int:log_id>/photos', type='http',
                auth='user', website=True)
    def upload_photos(self, log_id, **kwargs):
        supervisor = self._get_supervisor()
        log = request.env['contractor.work.log'].sudo().browse(log_id)
        if not log.exists() or log.supervisor_id.id != supervisor.id:
            return request.redirect('/contractor')
        return request.render('waqf_contractor_portal.tmpl_upload_photos', {
            'log': log,
            'supervisor': supervisor,
            'mosque': log.mosque_id,
        })

    @http.route('/contractor/work/<int:log_id>/photos/save', type='http',
                auth='user', website=True, methods=['POST'])
    def save_photos(self, log_id, **post):
        supervisor = self._get_supervisor()
        log = request.env['contractor.work.log'].sudo().browse(log_id)
        if not log.exists() or log.supervisor_id.id != supervisor.id:
            return request.redirect('/contractor')

        files = request.httprequest.files.getlist('photos')
        Attachment = request.env['ir.attachment'].sudo()

        for f in files:
            if f and f.filename:
                Attachment.create({
                    'name': f.filename,
                    'datas': base64.b64encode(f.read()),
                    'res_model': 'contractor.work.log',
                    'res_id': log.id,
                    'mimetype': f.content_type,
                })

        # Auto-submit if has photos
        if log.photo_ids:
            try:
                log.action_submit()
            except Exception:
                pass

        return request.redirect(
            '/contractor/task/%d?submitted=1' % (log.task_id.id or 0))

    # ── Change Order Request ──────────────────────────────────────
    @http.route('/contractor/change-order/new', type='http',
                auth='user', website=True)
    def change_order_form(self, log_id=None, **kwargs):
        supervisor = self._get_supervisor()
        mosque = supervisor.assigned_mosque_id if supervisor else None
        log = None
        if log_id:
            log = request.env['contractor.work.log'].sudo().browse(int(log_id))
        return request.render('waqf_contractor_portal.tmpl_change_order', {
            'supervisor': supervisor,
            'mosque': mosque,
            'log': log,
        })

    @http.route('/contractor/change-order/submit', type='http',
                auth='user', website=True, methods=['POST'])
    def submit_change_order(self, **post):
        supervisor = self._get_supervisor()
        mosque = supervisor.assigned_mosque_id

        co_type = post.get('type', 'scope')
        reason = post.get('reason', '').strip()
        amount = float(post.get('amount', 0) or 0)
        days = int(post.get('days_extension', 0) or 0)

        CO = request.env['mosque.change.order'].sudo()
        co = CO.create({
            'mosque_id': mosque.id,
            'type': co_type,
            'reason': reason,
            'amount': amount,
            'days_extension': days,
            'state': 'review',
        })

        # Link log if provided
        log_id = int(post.get('log_id', 0) or 0)
        if log_id:
            log = request.env['contractor.work.log'].sudo().browse(log_id)
            if log.exists():
                log.message_post(
                    body=_('Change order %s submitted.') % co.name)

        return request.redirect('/contractor?co_submitted=1')

    # ── Certificate Request ───────────────────────────────────────
    @http.route('/contractor/certificate/new', type='http',
                auth='user', website=True)
    def certificate_form(self, **kwargs):
        supervisor = self._get_supervisor()
        mosque = supervisor.assigned_mosque_id if supervisor else None
        if not mosque or not self._check_mosque_access(mosque.id):
            return request.redirect('/contractor')

        # Last cert number
        last_cert = request.env['mosque.certificate'].sudo().search([
            ('mosque_id', '=', mosque.id),
        ], order='cert_number desc', limit=1)
        next_num = (last_cert.cert_number + 1) if last_cert else 1

        # Approved work logs not yet certified
        logs = request.env['contractor.work.log'].sudo().search([
            ('mosque_id', '=', mosque.id),
            ('supervisor_id', '=', supervisor.id),
            ('state', '=', 'approved'),
        ])

        return request.render('waqf_contractor_portal.tmpl_certificate', {
            'supervisor': supervisor,
            'mosque': mosque,
            'next_num': next_num,
            'logs': logs,
        })

    @http.route('/contractor/certificate/submit', type='http',
                auth='user', website=True, methods=['POST'])
    def submit_certificate(self, **post):
        supervisor = self._get_supervisor()
        mosque = supervisor.assigned_mosque_id

        Cert = request.env['mosque.certificate'].sudo()
        CertLine = request.env['mosque.certificate.line'].sudo()

        cert = Cert.create({
            'mosque_id': mosque.id,
            'cert_number': int(post.get('cert_number', 1)),
            'period_from': post.get('period_from'),
            'period_to': post.get('period_to'),
            'submission_date': post.get('period_to'),
        })

        # Add lines from selected logs
        log_ids = request.httprequest.form.getlist('log_ids')
        for log_id in log_ids:
            log = request.env['contractor.work.log'].sudo().browse(int(log_id))
            if log.exists() and log.boq_id:
                CertLine.create({
                    'certificate_id': cert.id,
                    'boq_id': log.boq_id.id,
                    'this_period_qty': log.qty_executed,
                })

        # Submit to consultant
        cert.action_submit_to_consultant()

        return request.redirect('/contractor?cert_submitted=1')

    # ══════════════════════════════════════════════════════════════
    # WORK LOG HISTORY — سجل الأعمال الكامل
    # ══════════════════════════════════════════════════════════════
    @http.route('/contractor/logs', type='http', auth='user', website=True)
    def work_log_history(self, state=None, **kwargs):
        supervisor = self._get_supervisor()
        if not supervisor:
            return request.redirect('/contractor')

        mosque = supervisor.assigned_mosque_id
        if not mosque or not self._check_mosque_access(mosque.id):
            return request.redirect('/contractor')

        # Filter by state
        domain = [
            ('mosque_id', '=', mosque.id),
            ('supervisor_id', '=', supervisor.id),
        ]
        if state and state != 'all':
            domain.append(('state', '=', state))

        logs = request.env['contractor.work.log'].sudo().search(
            domain, order='log_date desc, id desc')

        # BOQ balance per item (all logs)
        all_logs = request.env['contractor.work.log'].sudo().search([
            ('mosque_id', '=', mosque.id),
            ('supervisor_id', '=', supervisor.id),
            ('state', 'in', ['submitted', 'approved']),
        ])

        boq_balance = {}
        for log in all_logs:
            bid = log.boq_id.id
            if bid not in boq_balance:
                boq_balance[bid] = {
                    'boq': log.boq_id,
                    'executed': 0.0,
                    'contracted': log.boq_id.contracted_qty,
                }
            boq_balance[bid]['executed'] += log.qty_executed

        # Financial summary
        approved_val = sum(l.line_value for l in logs if l.state == 'approved')
        pending_val = sum(l.line_value for l in logs if l.state == 'submitted')
        rejected_val = sum(l.line_value for l in logs if l.state == 'rejected')
        total_val = sum(l.line_value for l in logs)

        # Rejected logs needing action
        rejected_logs = request.env['contractor.work.log'].sudo().search([
            ('mosque_id', '=', mosque.id),
            ('supervisor_id', '=', supervisor.id),
            ('state', '=', 'rejected'),
        ])

        return request.render('waqf_contractor_portal.tmpl_log_history', {
            'supervisor': supervisor,
            'mosque': mosque,
            'logs': logs,
            'active_state': state or 'all',
            'boq_balance': list(boq_balance.values()),
            'approved_val': approved_val,
            'pending_val': pending_val,
            'rejected_val': rejected_val,
            'total_val': total_val,
            'rejected_count': len(rejected_logs),
        })

    # ══════════════════════════════════════════════════════════════
    # REJECTED WORK — عرض العمل المرفوض وتعديله
    # ══════════════════════════════════════════════════════════════
    @http.route('/contractor/work/<int:log_id>/rejected', type='http',
                auth='user', website=True)
    def view_rejected(self, log_id, **kwargs):
        supervisor = self._get_supervisor()
        if not supervisor:
            return request.redirect('/contractor')

        log = request.env['contractor.work.log'].sudo().browse(log_id)
        if not log.exists() or log.supervisor_id.id != supervisor.id:
            return request.redirect('/contractor')
        if log.state != 'rejected':
            return request.redirect('/contractor/logs')

        mosque = log.mosque_id
        boq_items = request.env['mosque.boq'].sudo().search([
            ('mosque_id', '=', mosque.id),
        ], order='category_id, sequence')

        return request.render('waqf_contractor_portal.tmpl_rejected_detail', {
            'supervisor': supervisor,
            'mosque': mosque,
            'log': log,
            'boq_items': boq_items,
        })

    @http.route('/contractor/work/<int:log_id>/resubmit', type='http',
                auth='user', website=True, methods=['POST'])
    def resubmit_work(self, log_id, **post):
        """
        Edit a rejected work log and resubmit.
        Updates description, qty, BOQ item, then redirects to photo upload.
        """
        supervisor = self._get_supervisor()
        log = request.env['contractor.work.log'].sudo().browse(log_id)

        if not log.exists() or log.supervisor_id.id != supervisor.id:
            return request.redirect('/contractor')
        if log.state != 'rejected':
            return request.redirect('/contractor/logs')

        new_name = post.get('name', '').strip()
        new_qty = float(post.get('qty_executed', 0) or 0)
        new_boq_id = int(post.get('boq_id', 0) or 0)
        new_location = post.get('location_detail', '').strip()
        note_to_cons = post.get('note_to_consultant', '').strip()

        if not new_name or new_qty <= 0 or not new_boq_id:
            return request.redirect(
                '/contractor/work/%d/rejected?error=missing' % log_id)

        # Reverse previous BOQ qty
        if log.boq_id:
            log.boq_id.executed_qty = max(
                0, log.boq_id.executed_qty - log.qty_executed)

        # Remove old photos so supervisor uploads fresh ones
        log.sudo().photo_ids.unlink()

        # Update log fields
        log.write({
            'name': new_name,
            'qty_executed': new_qty,
            'boq_id': new_boq_id,
            'location_detail': new_location,
            'state': 'draft',  # back to draft pending new photos
            'reject_reason': False,
        })

        # Post chatter note
        msg = _('تم تعديل العمل وإعادة التقديم.')
        if note_to_cons:
            msg += '<br/><b>ملاحظة للاستشاري:</b> %s' % note_to_cons
        log.message_post(body=msg)

        # Redirect to photo upload — same flow as new submission
        return request.redirect('/contractor/work/%d/photos' % log_id)

    @http.route('/contractor/work/<int:log_id>/cancel', type='http',
                auth='user', website=True, methods=['POST'])
    def cancel_rejected(self, log_id, **post):
        """Cancel a rejected work log."""
        supervisor = self._get_supervisor()
        log = request.env['contractor.work.log'].sudo().browse(log_id)

        if not log.exists() or log.supervisor_id.id != supervisor.id:
            return request.redirect('/contractor')
        if log.state != 'rejected':
            return request.redirect('/contractor/logs')

        log.message_post(body=_('تم إلغاء هذا العمل من قِبل المشرف.'))
        log.write({'state': 'draft'})  # soft cancel — stays visible but inactive

        return request.redirect('/contractor/logs?cancelled=1')

    # ══════════════════════════════════════════════════════
    # LIST — /contractor/work-orders
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/work-orders', type='http',
                auth='user', website=True)
    def work_orders_list(self, mosque=None, state=None, task=None, **kwargs):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        domain = self._wo_domain(portal_user, supervisor,
                                 int(mosque) if mosque else None)
        if state and state != 'all':
            domain.append(('state', '=', state))
        if task:
            domain.append(('task_id', '=', int(task)))

        work_orders = request.env['contractor.work.order'].sudo().search(
            domain, order='date_requested desc')

        # Mosque list for filter
        if portal_user:
            mosques = portal_user.effective_mosque_ids
        else:
            mosques = []

        return request.render('waqf_contractor_portal.tmpl_wo_list', {
            'portal_user': portal_user,
            'supervisor': supervisor,
            'work_orders': work_orders,
            'mosques': mosques,
            'active_state': state or 'all',
            'active_mosque': int(mosque) if mosque else None,
        })

    # ══════════════════════════════════════════════════════
    # NEW — /contractor/work-orders/new
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/work-orders/new', type='http',
                auth='user', website=True)
    def work_order_new(self, mosque=None, task=None, **kwargs):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        mosque_id = int(mosque) if mosque else None
        task_id = int(task) if task else None

        # BOQ categories & items
        boq_items = []
        selected_mosque = None
        tasks = []

        if mosque_id:
            selected_mosque, _ = self._resolve_mosque(mosque_id)
            if selected_mosque:
                boq_items = request.env['mosque.boq'].sudo().search([
                    ('mosque_id', '=', mosque_id),
                    ('remaining_qty', '>', 0),
                ], order='category_id, sequence')

                if selected_mosque.project_id:
                    tasks = request.env['project.task'].sudo().search([
                        ('project_id', '=', selected_mosque.project_id.id),
                        ('parent_id', '=', False),
                        ('stage_id.fold', '=', False),
                    ], order='date_deadline asc')

        # Approved qualifications
        qual_domain = []
        if supervisor:
            qual_domain.append(('supervisor_id', '=', supervisor.id))
        qualifications = request.env['contractor.qualification'].sudo().search(
            qual_domain + [('state', '=', 'approved')])

        # Available mosques
        if portal_user:
            mosques = portal_user.effective_mosque_ids
        else:
            mosques = []

        return request.render('waqf_contractor_portal.tmpl_wo_new', {
            'portal_user': portal_user,
            'supervisor': supervisor,
            'mosque': selected_mosque,
            'mosques': mosques,
            'boq_items': boq_items,
            'tasks': tasks,
            'qualifications': qualifications,
            'selected_task_id': task_id,
        })

    # ══════════════════════════════════════════════════════
    # CREATE — POST /contractor/work-orders/create
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/work-orders/create', type='http',
                auth='user', website=True, methods=['POST'])
    def work_order_create(self, **post):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        mosque_id = int(post.get('mosque_id', 0) or 0)
        task_id = int(post.get('task_id', 0) or 0)
        desc = post.get('work_description', '').strip()
        qual_id = int(post.get('qualification_id', 0) or 0)
        notes = post.get('commencement_notes', '').strip()
        date_start = post.get('date_planned_start') or False
        date_end = post.get('date_planned_end') or False

        if not mosque_id or not desc:
            return request.redirect('/contractor/work-orders/new?error=missing')

        mosque, _ = self._resolve_mosque(mosque_id)
        if not mosque:
            return request.redirect('/contractor')

        # جمع بنود BOQ
        boq_ids = request.httprequest.form.getlist('boq_ids')
        boq_qtys = request.httprequest.form.getlist('boq_qtys')

        if not boq_ids:
            return request.redirect(
                f'/contractor/work-orders/new?mosque={mosque_id}&error=no_boq')

        vals = {
            'mosque_id': mosque.id,
            'work_description': desc,
            'commencement_notes': notes,
            'date_planned_start': date_start,
            'date_planned_end': date_end,
        }
        if supervisor:
            vals['supervisor_id'] = supervisor.id
        if portal_user:
            vals['portal_user_id'] = portal_user.user_id.id
        if task_id:
            vals['task_id'] = task_id
        if qual_id:
            vals['qualification_id'] = qual_id

        WO = request.env['contractor.work.order'].sudo()
        wo = WO.create(vals)

        # إضافة بنود BOQ
        for bid, qty in zip(boq_ids, boq_qtys):
            try:
                request.env['contractor.work.order.boq'].sudo().create({
                    'work_order_id': wo.id,
                    'boq_id': int(bid),
                    'qty_requested': float(qty or 0),
                })
            except Exception:
                pass

        # رفع صور الموقع
        files = request.httprequest.files.getlist('site_photos')
        for f in files:
            if f and f.filename:
                att = request.env['ir.attachment'].sudo().create({
                    'name': f.filename,
                    'datas': base64.b64encode(f.read()),
                    'res_model': 'contractor.work.order',
                    'res_id': wo.id,
                    'mimetype': f.content_type,
                })
                wo.write({'site_photo_ids': [(4, att.id)]})

        return request.redirect(f'/contractor/work-order/{wo.id}?created=1')

    # ══════════════════════════════════════════════════════
    # DETAIL — /contractor/work-order/<id>
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/work-order/<int:wo_id>', type='http',
                auth='user', website=True)
    def work_order_detail(self, wo_id, **kwargs):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        wo = request.env['contractor.work.order'].sudo().browse(wo_id)
        if not wo.exists():
            return request.redirect('/contractor/work-orders')

        # تحقق من الصلاحية
        if portal_user:
            if wo.portal_user_id != portal_user.user_id:
                return request.redirect('/contractor/work-orders')
        elif supervisor:
            if wo.supervisor_id != supervisor:
                return request.redirect('/contractor/work-orders')

        return request.render('waqf_contractor_portal.tmpl_wo_detail', {
            'portal_user': portal_user,
            'supervisor': supervisor,
            'mosque': wo.mosque_id,
            'wo': wo,
        })

    # ══════════════════════════════════════════════════════
    # SUBMIT COMMENCEMENT
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/work-order/<int:wo_id>/submit-commencement',
                type='http', auth='user', website=True, methods=['POST'])
    def submit_commencement(self, wo_id, **post):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()
        wo = request.env['contractor.work.order'].sudo().browse(wo_id)
        if not wo.exists():
            return request.redirect('/contractor/work-orders')
        try:
            wo.action_submit_commencement()
        except UserError as e:
            return request.redirect(
                f'/contractor/work-order/{wo_id}?error={str(e)[:80]}')
        return request.redirect(f'/contractor/work-order/{wo_id}?submitted=1')

    # ══════════════════════════════════════════════════════
    # SUBMIT DELIVERY
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/work-order/<int:wo_id>/submit-delivery',
                type='http', auth='user', website=True, methods=['POST'])
    def submit_delivery(self, wo_id, **post):
        wo = request.env['contractor.work.order'].sudo().browse(wo_id)
        if not wo.exists():
            return request.redirect('/contractor/work-orders')

        notes = post.get('delivery_notes', '').strip()
        if notes:
            wo.write({'delivery_notes': notes})

        # رفع صور التسليم
        files = request.httprequest.files.getlist('delivery_photos')
        for f in files:
            if f and f.filename:
                att = request.env['ir.attachment'].sudo().create({
                    'name': f.filename,
                    'datas': base64.b64encode(f.read()),
                    'res_model': 'contractor.work.order',
                    'res_id': wo.id,
                    'mimetype': f.content_type,
                })
                wo.write({'delivery_photo_ids': [(4, att.id)]})

        try:
            wo.action_submit_delivery()
        except UserError as e:
            return request.redirect(
                f'/contractor/work-order/{wo_id}?error={str(e)[:80]}')
        return request.redirect(f'/contractor/work-order/{wo_id}?delivered=1')

    # ══════════════════════════════════════════════════════
    # REWORK — إعادة العمل
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/work-order/<int:wo_id>/rework-submit',
                type='http', auth='user', website=True, methods=['POST'])
    def rework_submit(self, wo_id, **post):
        wo = request.env['contractor.work.order'].sudo().browse(wo_id)
        if not wo.exists() or wo.state != 'rework':
            return request.redirect('/contractor/work-orders')

        notes = post.get('rework_notes', '').strip()

        # أحدّث آخر سجل rework
        last_rework = wo.rework_log_ids.sorted('date', reverse=True)[:1]
        if last_rework:
            files = request.httprequest.files.getlist('rework_photos')
            att_ids = []
            for f in files:
                if f and f.filename:
                    att = request.env['ir.attachment'].sudo().create({
                        'name': f.filename,
                        'datas': base64.b64encode(f.read()),
                        'res_model': 'contractor.work.order.rework',
                        'res_id': last_rework.id,
                        'mimetype': f.content_type,
                    })
                    att_ids.append(att.id)
            last_rework.write({
                'resolved': True,
                'resolved_date': date.today(),
                'photo_ids': [(4, i) for i in att_ids],
            })

        # إرسال التسليم مجدداً
        if notes:
            wo.write({'delivery_notes': notes})
        try:
            wo.action_submit_delivery()
        except UserError as e:
            return request.redirect(
                f'/contractor/work-order/{wo_id}?error={str(e)[:80]}')
        return request.redirect(f'/contractor/work-order/{wo_id}?rework_done=1')

    # ══════════════════════════════════════════════════════
    # SUBMITTALS — عينات المواد
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/submittals/new', type='http',
                auth='user', website=True)
    def submittal_new(self, mosque=None, wo=None, **kwargs):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        mosque_id = int(mosque) if mosque else None
        wo_id = int(wo) if wo else None

        boq_items = []
        if mosque_id:
            boq_items = request.env['mosque.boq'].sudo().search([
                ('mosque_id', '=', mosque_id),
                # ('requires_sample', '=', True),
            ])

        work_order = None
        if wo_id:
            work_order = request.env['contractor.work.order'].sudo().browse(wo_id)

        return request.render('waqf_contractor_portal.tmpl_submittal_new', {
            'portal_user': portal_user,
            'supervisor': supervisor,
            'boq_items': boq_items,
            'work_order': work_order,
            'mosque_id': mosque_id,
        })

    @http.route('/contractor/submittals/create', type='http',
                auth='user', website=True, methods=['POST'])
    def submittal_create(self, **post):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        wo_id = int(post.get('work_order_id', 0) or 0)
        boq_id = int(post.get('boq_id', 0) or 0)
        material_name = post.get('material_name', '').strip()
        manufacturer = post.get('manufacturer', '').strip()
        model_number = post.get('model_number', '').strip()
        specs = post.get('specifications', '').strip()
        mosque_id = int(post.get('mosque_id', 0) or 0)

        if not boq_id or not material_name:
            return request.redirect('/contractor/submittals/new?error=missing')

        vals = {
            'boq_id': boq_id,
            'material_name': material_name,
            'manufacturer': manufacturer,
            'model_number': model_number,
            'specifications': specs,
        }
        if mosque_id:
            vals['mosque_id'] = mosque_id
        if wo_id:
            vals['work_order_id'] = wo_id

        sub = request.env['contractor.material.submittal'].sudo().create(vals)

        # رفع الوثائق
        files = request.httprequest.files.getlist('documents')
        for f in files:
            if f and f.filename:
                att = request.env['ir.attachment'].sudo().create({
                    'name': f.filename,
                    'datas': base64.b64encode(f.read()),
                    'res_model': 'contractor.material.submittal',
                    'res_id': sub.id,
                    'mimetype': f.content_type,
                })
                sub.write({'document_ids': [(4, att.id)]})

        # إرسال مباشر
        try:
            sub.action_submit()
        except Exception:
            pass

        redirect = f'/contractor/work-order/{wo_id}' if wo_id else '/contractor'
        return request.redirect(f'{redirect}?sub_submitted=1')

    # ══════════════════════════════════════════════════════
    # QUALIFICATIONS
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/qualifications/new', type='http',
                auth='user', website=True)
    def qualification_new(self, **kwargs):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        categories = request.env['mosque.boq.category'].sudo().search([])

        if portal_user:
            mosques = portal_user.effective_mosque_ids
        else:
            mosques = []

        return request.render('waqf_contractor_portal.tmpl_qualification_new', {
            'portal_user': portal_user,
            'supervisor': supervisor,
            'categories': categories,
            'mosques': mosques,
        })

    @http.route('/contractor/qualifications/create', type='http',
                auth='user', website=True, methods=['POST'])
    def qualification_create(self, **post):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()
        if not supervisor and not portal_user:
            return request.redirect('/web')

        category_id = int(post.get('work_category_id', 0) or 0)
        scope = post.get('scope', 'all')
        desc = post.get('description', '').strip()
        mosque_ids = [int(i) for i in
                      request.httprequest.form.getlist('mosque_ids')]

        if not category_id:
            return request.redirect('/contractor/qualifications/new?error=missing')

        vals = {
            'work_category_id': category_id,
            'scope': scope,
            'description': desc,
        }
        if supervisor:
            vals['supervisor_id'] = supervisor.id
        if mosque_ids and scope == 'specific':
            vals['mosque_ids'] = [(6, 0, mosque_ids)]

        qual = request.env['contractor.qualification'].sudo().create(vals)

        # رفع الوثائق
        files = request.httprequest.files.getlist('documents')
        for f in files:
            if f and f.filename:
                att = request.env['ir.attachment'].sudo().create({
                    'name': f.filename,
                    'datas': base64.b64encode(f.read()),
                    'res_model': 'contractor.qualification',
                    'res_id': qual.id,
                    'mimetype': f.content_type,
                })
                qual.write({'document_ids': [(4, att.id)]})

        try:
            qual.action_submit()
        except Exception:
            pass

        return request.redirect('/contractor?qual_submitted=1')
