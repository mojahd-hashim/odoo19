# -*- coding: utf-8 -*-
from odoo import http, _
from odoo.http import request
from odoo.exceptions import UserError
from datetime import date
import base64


class ContractorWorkOrderPortal(http.Controller):
    """
    بوابة أوامر العمل للمقاول
    """

    def _get_portal_user(self):
        contractor_roles = ['site_supervisor', 'contractor_admin', 'contractor_engineer']
        return request.env['waqf.portal.user'].sudo().search([
            ('user_id',   '=', request.env.user.id),
            ('role',      'in', contractor_roles),
            ('is_active', '=', True),
        ], limit=1) or None

    def _get_supervisor(self):
        portal_user = self._get_portal_user()
        if portal_user:
            return portal_user.user_id.partner_id
        partner = request.env.user.partner_id
        return partner if partner.contractor_supervisor else None

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

    # ══════════════════════════════════════════════════════
    # LIST — /contractor/work-orders
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/work-orders', type='http',
                auth='user', website=True)
    def work_orders_list(self, mosque=None, state=None, task=None, **kwargs):
        portal_user = self._get_portal_user()
        supervisor  = self._get_supervisor()
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
            'portal_user':  portal_user,
            'supervisor':   supervisor,
            'work_orders':  work_orders,
            'mosques':      mosques,
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
        supervisor  = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        mosque_id = int(mosque) if mosque else None
        task_id   = int(task)   if task   else None

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
                        ('parent_id',  '=', False),
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
            'portal_user':       portal_user,
            'supervisor':        supervisor,
            'mosque':            selected_mosque,
            'mosques':           mosques,
            'boq_items':         boq_items,
            'tasks':             tasks,
            'qualifications':    qualifications,
            'selected_task_id':  task_id,
        })

    # ══════════════════════════════════════════════════════
    # CREATE — POST /contractor/work-orders/create
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/work-orders/create', type='http',
                auth='user', website=True, methods=['POST'])
    def work_order_create(self, **post):
        portal_user = self._get_portal_user()
        supervisor  = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        mosque_id   = int(post.get('mosque_id', 0) or 0)
        task_id     = int(post.get('task_id', 0) or 0)
        desc        = post.get('work_description', '').strip()
        qual_id     = int(post.get('qualification_id', 0) or 0)
        notes       = post.get('commencement_notes', '').strip()
        date_start  = post.get('date_planned_start') or False
        date_end    = post.get('date_planned_end')   or False

        if not mosque_id or not desc:
            return request.redirect('/contractor/work-orders/new?error=missing')

        mosque, _ = self._resolve_mosque(mosque_id)
        if not mosque:
            return request.redirect('/contractor')

        # جمع بنود BOQ
        boq_ids  = request.httprequest.form.getlist('boq_ids')
        boq_qtys = request.httprequest.form.getlist('boq_qtys')

        if not boq_ids:
            return request.redirect(
                f'/contractor/work-orders/new?mosque={mosque_id}&error=no_boq')

        vals = {
            'mosque_id':           mosque.id,
            'work_description':    desc,
            'commencement_notes':  notes,
            'date_planned_start':  date_start,
            'date_planned_end':    date_end,
        }
        if supervisor:
            vals['supervisor_id']    = supervisor.id
        if portal_user:
            vals['portal_user_id']   = portal_user.user_id.id
        if task_id:
            vals['task_id']          = task_id
        if qual_id:
            vals['qualification_id'] = qual_id

        WO = request.env['contractor.work.order'].sudo()
        wo = WO.create(vals)

        # إضافة بنود BOQ
        for bid, qty in zip(boq_ids, boq_qtys):
            try:
                request.env['contractor.work.order.boq'].sudo().create({
                    'work_order_id': wo.id,
                    'boq_id':        int(bid),
                    'qty_requested': float(qty or 0),
                })
            except Exception:
                pass

        # رفع صور الموقع
        files = request.httprequest.files.getlist('site_photos')
        for f in files:
            if f and f.filename:
                att = request.env['ir.attachment'].sudo().create({
                    'name':      f.filename,
                    'datas':     base64.b64encode(f.read()),
                    'res_model': 'contractor.work.order',
                    'res_id':    wo.id,
                    'mimetype':  f.content_type,
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
        supervisor  = self._get_supervisor()
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
            'supervisor':  supervisor,
            'mosque':      wo.mosque_id,
            'wo':          wo,
        })

    # ══════════════════════════════════════════════════════
    # SUBMIT COMMENCEMENT
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/work-order/<int:wo_id>/submit-commencement',
                type='http', auth='user', website=True, methods=['POST'])
    def submit_commencement(self, wo_id, **post):
        portal_user = self._get_portal_user()
        supervisor  = self._get_supervisor()
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
                    'name':      f.filename,
                    'datas':     base64.b64encode(f.read()),
                    'res_model': 'contractor.work.order',
                    'res_id':    wo.id,
                    'mimetype':  f.content_type,
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
                        'name':      f.filename,
                        'datas':     base64.b64encode(f.read()),
                        'res_model': 'contractor.work.order.rework',
                        'res_id':    last_rework.id,
                        'mimetype':  f.content_type,
                    })
                    att_ids.append(att.id)
            last_rework.write({
                'resolved':      True,
                'resolved_date': date.today(),
                'photo_ids':     [(4, i) for i in att_ids],
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
        supervisor  = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        mosque_id = int(mosque) if mosque else None
        wo_id     = int(wo)     if wo     else None

        boq_items = []
        if mosque_id:
            boq_items = request.env['mosque.boq'].sudo().search([
                ('mosque_id',       '=', mosque_id),
                ('requires_sample', '=', True),
            ])

        work_order = None
        if wo_id:
            work_order = request.env['contractor.work.order'].sudo().browse(wo_id)

        return request.render('waqf_contractor_portal.tmpl_submittal_new', {
            'portal_user': portal_user,
            'supervisor':  supervisor,
            'boq_items':   boq_items,
            'work_order':  work_order,
            'mosque_id':   mosque_id,
        })

    @http.route('/contractor/submittals/create', type='http',
                auth='user', website=True, methods=['POST'])
    def submittal_create(self, **post):
        portal_user = self._get_portal_user()
        supervisor  = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        wo_id         = int(post.get('work_order_id', 0) or 0)
        boq_id        = int(post.get('boq_id', 0) or 0)
        material_name = post.get('material_name', '').strip()
        manufacturer  = post.get('manufacturer', '').strip()
        model_number  = post.get('model_number', '').strip()
        specs         = post.get('specifications', '').strip()

        if not boq_id or not material_name:
            return request.redirect('/contractor/submittals/new?error=missing')

        vals = {
            'boq_id':        boq_id,
            'material_name': material_name,
            'manufacturer':  manufacturer,
            'model_number':  model_number,
            'specifications': specs,
        }
        if wo_id:
            vals['work_order_id'] = wo_id

        sub = request.env['contractor.material.submittal'].sudo().create(vals)

        # رفع الوثائق
        files = request.httprequest.files.getlist('documents')
        for f in files:
            if f and f.filename:
                att = request.env['ir.attachment'].sudo().create({
                    'name':      f.filename,
                    'datas':     base64.b64encode(f.read()),
                    'res_model': 'contractor.material.submittal',
                    'res_id':    sub.id,
                    'mimetype':  f.content_type,
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
        supervisor  = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        categories = request.env['mosque.boq.category'].sudo().search([])

        if portal_user:
            mosques = portal_user.effective_mosque_ids
        else:
            mosques = []

        return request.render('waqf_contractor_portal.tmpl_qualification_new', {
            'portal_user': portal_user,
            'supervisor':  supervisor,
            'categories':  categories,
            'mosques':     mosques,
        })

    @http.route('/contractor/qualifications/create', type='http',
                auth='user', website=True, methods=['POST'])
    def qualification_create(self, **post):
        portal_user = self._get_portal_user()
        supervisor  = self._get_supervisor()
        if not supervisor and not portal_user:
            return request.redirect('/web')

        category_id = int(post.get('work_category_id', 0) or 0)
        scope       = post.get('scope', 'all')
        desc        = post.get('description', '').strip()
        mosque_ids  = [int(i) for i in
                       request.httprequest.form.getlist('mosque_ids')]

        if not category_id:
            return request.redirect('/contractor/qualifications/new?error=missing')

        vals = {
            'work_category_id': category_id,
            'scope':            scope,
            'description':      desc,
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
                    'name':      f.filename,
                    'datas':     base64.b64encode(f.read()),
                    'res_model': 'contractor.qualification',
                    'res_id':    qual.id,
                    'mimetype':  f.content_type,
                })
                qual.write({'document_ids': [(4, att.id)]})

        try:
            qual.action_submit()
        except Exception:
            pass

        return request.redirect('/contractor?qual_submitted=1')