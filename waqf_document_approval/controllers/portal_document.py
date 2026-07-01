# -*- coding: utf-8 -*-
import base64
from odoo import http, _
from odoo.http import request


class DocumentApprovalPortal(http.Controller):

    def _get_portal_user(self):
        roles = ['site_supervisor', 'contractor_admin', 'contractor_engineer']
        return request.env['waqf.portal.user'].sudo().search([
            ('user_id', '=', request.env.user.id),
            ('role', 'in', roles),
            ('is_active', '=', True),
        ], limit=1) or None

    def _get_supervisor(self):
        pu = self._get_portal_user()
        if pu:
            return pu.user_id.partner_id
        partner = request.env.user.partner_id
        return partner if partner.contractor_supervisor else None

    # ══════════════════════════════════════════════════════
    # LIST — /contractor/documents
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/documents', type='http',
                auth='user', website=True)
    def documents_list(self, state=None, **kw):
        portal_user = self._get_portal_user()
        supervisor  = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        domain = [('submitted_by', '=', request.env.user.id)]
        if portal_user.role in ['contractor_admin']:
            domain = []
        if state and state != 'all':
            domain.append(('state', '=', state))

        docs = request.env['waqf.document.approval'].sudo().search(
            domain, order='create_date desc')

        all_docs = request.env['waqf.document.approval'].sudo().search([
            ('submitted_by', '=', request.env.user.id)])

        if portal_user.role in ['contractor_admin']:
            all_docs = request.env['waqf.document.approval'].sudo().search([])
        counts = {
            'all':       len(all_docs),
            'draft':     sum(1 for d in all_docs if d.state == 'draft'),
            'submitted': sum(1 for d in all_docs if d.state == 'submitted'),
            'approved':  sum(1 for d in all_docs if d.state in ('approved', 'approved_comments')),
            'rejected':  sum(1 for d in all_docs if d.state == 'rejected'),
        }

        return request.render('waqf_document_approval.tmpl_doc_list', {
            'portal_user': portal_user,
            'documents':   docs,
            'active_state':state or 'all',
            'counts':      counts,
        })

    # ══════════════════════════════════════════════════════
    # NEW — /contractor/documents/new
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/documents/new', type='http',
                auth='user', website=True)
    def document_new(self, **kw):
        portal_user = self._get_portal_user()
        supervisor  = self._get_supervisor()
        if not portal_user and not supervisor:
            return request.redirect('/web')

        doc_types = request.env['waqf.document.type'].sudo().search([])
        if portal_user:
            mosques = portal_user.effective_mosque_ids
        elif supervisor and supervisor.assigned_mosque_id:
            mosques = supervisor.assigned_mosque_id
        else:
            mosques = []

        return request.render('waqf_document_approval.tmpl_doc_new', {
            'portal_user': portal_user,
            'doc_types':   doc_types,
            'mosques':     mosques,
        })

    # ══════════════════════════════════════════════════════
    # CREATE — POST — ينشئ الطلب كمسودة
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/documents/create', type='http',
                auth='user', website=True, methods=['POST'])
    def document_create(self, **post):
        if not self._get_portal_user() and not self._get_supervisor():
            return request.redirect('/web')

        title       = post.get('title', '').strip()
        mosque_id   = int(post.get('mosque_id', 0) or 0)
        doc_type_id = int(post.get('doc_type_id', 0) or 0)
        desc        = post.get('description', '').strip()

        if not title or not mosque_id or not doc_type_id:
            return request.redirect('/contractor/documents/new?error=missing')

        doc = request.env['waqf.document.approval'].sudo().create({
            'title':       title,
            'mosque_id':   mosque_id,
            'doc_type_id': doc_type_id,
            'description': desc,
        })

        # رفع الملف الأول
        self._attach_file(doc, post)

        # توجيه لصفحة الرفع المتتابع
        return request.redirect('/contractor/documents/%d/upload' % doc.id)

    # ══════════════════════════════════════════════════════
    # UPLOAD PAGE — رفع ملف-ملف
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/documents/<int:doc_id>/upload', type='http',
                auth='user', website=True)
    def document_upload_page(self, doc_id, **kw):
        doc = request.env['waqf.document.approval'].sudo().browse(doc_id)
        if not doc.exists() or doc.submitted_by.id != request.env.user.id:
            return request.redirect('/contractor/documents')
        if doc.state != 'draft':
            return request.redirect('/contractor/documents/%d' % doc_id)

        return request.render('waqf_document_approval.tmpl_doc_upload', {
            'doc': doc,
        })

    # ══════════════════════════════════════════════════════
    # ADD FILE — POST — يضيف ملف ثم يسأل: أخير أم لا؟
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/documents/<int:doc_id>/add-file', type='http',
                auth='user', website=True, methods=['POST'])
    def document_add_file(self, doc_id, **post):
        doc = request.env['waqf.document.approval'].sudo().browse(doc_id)
        if not doc.exists() or doc.submitted_by.id != request.env.user.id:
            return request.redirect('/contractor/documents')
        if doc.state != 'draft':
            return request.redirect('/contractor/documents/%d' % doc_id)

        self._attach_file(doc, post)

        is_final = post.get('is_final') == '1'
        if is_final:
            # إرسال الطلب مباشرة
            try:
                doc.action_submit()
            except Exception:
                pass
            return request.redirect(
                '/contractor/documents/%d?submitted=1' % doc_id)

        # العودة لصفحة الرفع لإضافة ملف آخر
        return request.redirect(
            '/contractor/documents/%d/upload?added=1' % doc_id)

    def _attach_file(self, doc, post):
        """يرفع ملفاً ويخزّنه على القرص عبر ir.attachment."""
        f = request.httprequest.files.get('document_file')
        if not f or not f.filename:
            return
        note = post.get('file_note', '').strip()

        # إنشاء ir.attachment (Odoo يخزّنه في filestore على القرص تلقائياً)
        att = request.env['ir.attachment'].sudo().create({
            'name':      f.filename,
            'datas':     base64.b64encode(f.read()),
            'res_model': 'waqf.document.approval',
            'res_id':    doc.id,
            'mimetype':  f.content_type,
        })
        request.env['waqf.document.approval.file'].sudo().create({
            'approval_id':   doc.id,
            'name':          f.filename,
            'attachment_id': att.id,
            'note':          note,
            'sequence':      (len(doc.file_ids) + 1) * 10,
        })

    # ══════════════════════════════════════════════════════
    # DELETE FILE
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/documents/<int:doc_id>/delete-file/<int:file_id>',
                type='http', auth='user', website=True, methods=['POST'])
    def document_delete_file(self, doc_id, file_id, **kw):
        doc = request.env['waqf.document.approval'].sudo().browse(doc_id)
        if doc.exists() and doc.submitted_by.id == request.env.user.id \
                and doc.state == 'draft':
            f = request.env['waqf.document.approval.file'].sudo().browse(file_id)
            if f.exists() and f.approval_id.id == doc_id:
                f.unlink()
        return request.redirect('/contractor/documents/%d/upload' % doc_id)

    # ══════════════════════════════════════════════════════
    # DETAIL
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/documents/<int:doc_id>', type='http',
                auth='user', website=True)
    def document_detail(self, doc_id, **kw):
        doc = request.env['waqf.document.approval'].sudo().browse(doc_id)
        if not doc.exists() or doc.submitted_by.id != request.env.user.id:
            return request.redirect('/contractor/documents')

        return request.render('waqf_document_approval.tmpl_doc_detail', {
            'doc': doc,
        })

    # ══════════════════════════════════════════════════════
    # RESUBMIT — فتح طلب مرفوض
    # ══════════════════════════════════════════════════════
    @http.route('/contractor/documents/<int:doc_id>/resubmit', type='http',
                auth='user', website=True, methods=['POST'])
    def document_resubmit(self, doc_id, **kw):
        doc = request.env['waqf.document.approval'].sudo().browse(doc_id)
        if doc.exists() and doc.submitted_by.id == request.env.user.id \
                and doc.state == 'rejected':
            doc.action_resubmit()
            return request.redirect('/contractor/documents/%d/upload' % doc_id)
        return request.redirect('/contractor/documents/%d' % doc_id)
