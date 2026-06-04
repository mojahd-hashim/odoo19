from odoo import http, _
from odoo.http import request
from odoo.exceptions import AccessError, UserError
from datetime import date, timedelta
import base64
import json


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

    @http.route('/contractor', type='http', auth='user', website=True)
    def portal_home(self, **kwargs):
        # ── تحقق من الصلاحية ─────────────────────────────────
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()

        if not portal_user and not supervisor:
            return request.redirect('/web')

        # ── قائمة المساجد المتاحة ─────────────────────────────
        if portal_user:
            mosques = portal_user.effective_mosque_ids.sorted('name')
            is_admin = portal_user.role == 'contractor_admin'
        else:
            # النظام القديم — مسجد واحد
            mosque = supervisor.assigned_mosque_id
            if mosque:
                return request.redirect(f'/contractor/mosque/{mosque.id}')
            return request.render('waqf_contractor_portal.tmpl_no_mosque', {})

        # إذا كان لديه مسجد واحد فقط — انتقل مباشرة
        if len(mosques) == 1:
            return request.redirect(f'/contractor/mosque/{mosques[0].id}')

        return request.render('waqf_contractor_portal.tmpl_mosque_select', {
            'portal_user': portal_user,
            'mosques': mosques,
            'is_admin': is_admin,
        })

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
            has_access = portal_user.permission_id[:1].can_submit_works
        else:
            has_access = self._check_mosque_access(mosque_id)

        # باقي المحتوى — نفس الكود الموجود
        tasks = []
        if mosque.project_id:
            tasks = request.env['project.task'].sudo().search([
                ('project_id', '=', mosque.project_id.id),
                ('parent_id', '=', False),
            ], order='date_deadline asc')

        recent_logs = request.env['contractor.work.log'].sudo().search([
                                                                           ('mosque_id', '=', mosque.id),
                                                                       ] + ([('supervisor_id', '=',
                                                                              supervisor.id)] if supervisor else []),
                                                                       limit=5, order='log_date desc')

        rejected_logs = request.env['contractor.work.log'].sudo().search([
                                                                             ('mosque_id', '=', mosque.id),
                                                                             ('state', '=', 'rejected'),
                                                                         ] + ([('supervisor_id', '=',
                                                                                supervisor.id)] if supervisor else []),
                                                                         ) if has_access else []

        return request.render('waqf_contractor_portal.tmpl_home', {
            'supervisor': supervisor,
            'portal_user': portal_user,
            'mosque': mosque,
            'has_access': has_access,
            'tasks': tasks,
            'recent_logs': recent_logs,
            'rejected_logs': rejected_logs,
        })

    @http.route('/contractor/task/<int:task_id>', type='http',
                auth='user', website=True)
    def task_detail(self, task_id, **kwargs):
        portal_user = self._get_portal_user()
        supervisor = self._get_supervisor()

        if not portal_user and not supervisor:
            return request.redirect('/contractor')

        task = request.env['project.task'].sudo().browse(task_id)
        if not task.exists():
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
        task_id  = int(post.get('task_id', 0))
        boq_id   = int(post.get('boq_id', 0))
        qty      = float(post.get('qty_executed', 0))
        desc     = post.get('name', '').strip()
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
        needs_co  = total_qty > boq.contracted_qty * 1.10

        WorkLog = request.env['contractor.work.log'].sudo()
        log = WorkLog.create({
            'name':            desc,
            'mosque_id':       mosque.id,
            'supervisor_id':   supervisor.id,
            'boq_id':          boq_id,
            'task_id':         task_id,
            'log_date':        post.get('log_date'),
            'qty_executed':    qty,
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
                    'name':      f.filename,
                    'datas':     base64.b64encode(f.read()),
                    'res_model': 'contractor.work.log',
                    'res_id':    log.id,
                    'mimetype':  f.content_type,
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
            'mosque':     mosque,
            'log':        log,
        })

    @http.route('/contractor/change-order/submit', type='http',
                auth='user', website=True, methods=['POST'])
    def submit_change_order(self, **post):
        supervisor = self._get_supervisor()
        mosque = supervisor.assigned_mosque_id

        co_type = post.get('type', 'scope')
        reason  = post.get('reason', '').strip()
        amount  = float(post.get('amount', 0) or 0)
        days    = int(post.get('days_extension', 0) or 0)

        CO = request.env['mosque.change.order'].sudo()
        co = CO.create({
            'mosque_id':       mosque.id,
            'type':            co_type,
            'reason':          reason,
            'amount':          amount,
            'days_extension':  days,
            'state':           'review',
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
            ('mosque_id',     '=', mosque.id),
            ('supervisor_id', '=', supervisor.id),
            ('state',         '=', 'approved'),
        ])

        return request.render('waqf_contractor_portal.tmpl_certificate', {
            'supervisor': supervisor,
            'mosque':     mosque,
            'next_num':   next_num,
            'logs':       logs,
        })

    @http.route('/contractor/certificate/submit', type='http',
                auth='user', website=True, methods=['POST'])
    def submit_certificate(self, **post):
        supervisor = self._get_supervisor()
        mosque = supervisor.assigned_mosque_id

        Cert     = request.env['mosque.certificate'].sudo()
        CertLine = request.env['mosque.certificate.line'].sudo()

        cert = Cert.create({
            'mosque_id':       mosque.id,
            'cert_number':     int(post.get('cert_number', 1)),
            'period_from':     post.get('period_from'),
            'period_to':       post.get('period_to'),
            'submission_date': post.get('period_to'),
        })

        # Add lines from selected logs
        log_ids = request.httprequest.form.getlist('log_ids')
        for log_id in log_ids:
            log = request.env['contractor.work.log'].sudo().browse(int(log_id))
            if log.exists() and log.boq_id:
                CertLine.create({
                    'certificate_id':  cert.id,
                    'boq_id':          log.boq_id.id,
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
            ('mosque_id',     '=', mosque.id),
            ('supervisor_id', '=', supervisor.id),
        ]
        if state and state != 'all':
            domain.append(('state', '=', state))

        logs = request.env['contractor.work.log'].sudo().search(
            domain, order='log_date desc, id desc')

        # BOQ balance per item (all logs)
        all_logs = request.env['contractor.work.log'].sudo().search([
            ('mosque_id',     '=', mosque.id),
            ('supervisor_id', '=', supervisor.id),
            ('state', 'in', ['submitted', 'approved']),
        ])

        boq_balance = {}
        for log in all_logs:
            bid = log.boq_id.id
            if bid not in boq_balance:
                boq_balance[bid] = {
                    'boq':       log.boq_id,
                    'executed':  0.0,
                    'contracted': log.boq_id.contracted_qty,
                }
            boq_balance[bid]['executed'] += log.qty_executed

        # Financial summary
        approved_val  = sum(l.line_value for l in logs if l.state == 'approved')
        pending_val   = sum(l.line_value for l in logs if l.state == 'submitted')
        rejected_val  = sum(l.line_value for l in logs if l.state == 'rejected')
        total_val     = sum(l.line_value for l in logs)

        # Rejected logs needing action
        rejected_logs = request.env['contractor.work.log'].sudo().search([
            ('mosque_id',     '=', mosque.id),
            ('supervisor_id', '=', supervisor.id),
            ('state',         '=', 'rejected'),
        ])

        return request.render('waqf_contractor_portal.tmpl_log_history', {
            'supervisor':    supervisor,
            'mosque':        mosque,
            'logs':          logs,
            'active_state':  state or 'all',
            'boq_balance':   list(boq_balance.values()),
            'approved_val':  approved_val,
            'pending_val':   pending_val,
            'rejected_val':  rejected_val,
            'total_val':     total_val,
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

        mosque  = log.mosque_id
        boq_items = request.env['mosque.boq'].sudo().search([
            ('mosque_id', '=', mosque.id),
        ], order='category_id, sequence')

        return request.render('waqf_contractor_portal.tmpl_rejected_detail', {
            'supervisor': supervisor,
            'mosque':     mosque,
            'log':        log,
            'boq_items':  boq_items,
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

        new_name     = post.get('name', '').strip()
        new_qty      = float(post.get('qty_executed', 0) or 0)
        new_boq_id   = int(post.get('boq_id', 0) or 0)
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
            'name':            new_name,
            'qty_executed':    new_qty,
            'boq_id':          new_boq_id,
            'location_detail': new_location,
            'state':           'draft',   # back to draft pending new photos
            'reject_reason':   False,
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
        log.write({'state': 'draft'})   # soft cancel — stays visible but inactive

        return request.redirect('/contractor/logs?cancelled=1')
