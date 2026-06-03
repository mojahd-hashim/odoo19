# -*- coding: utf-8 -*-
"""
Helper: check portal user permissions from other modules.
Usage:
    from odoo.addons.waqf_portal_access.controllers.invite import get_portal_permissions
    perms = get_portal_permissions(env, user_id)
"""
from odoo import http
from odoo.http import request


def get_portal_permissions(env, user_id):
    """Returns permission dict for a given res.users id."""
    portal_user = env['waqf.portal.user'].sudo().search(
        [('user_id', '=', user_id), ('is_active', '=', True)], limit=1)
    if not portal_user:
        return {}
    perm = portal_user.permission_id[:1]
    if not perm:
        return {}
    return {
        'role':                     portal_user.role,
        'mosque_ids':               portal_user.effective_mosque_ids.ids,
        'can_submit_report':        perm.can_submit_report,
        'allowed_report_types':     perm.allowed_report_types.mapped('code'),
        'can_view_all_reports':     perm.can_view_all_reports,
        'can_approve_works':        perm.can_approve_works,
        'can_reject_works':         perm.can_reject_works,
        'can_view_boq_prices':      perm.can_view_boq_prices,
        'can_review_certificates':  perm.can_review_certificates,
        'can_approve_certificates': perm.can_approve_certificates,
        'can_submit_works':         perm.can_submit_works,
        'can_view_team_works':      perm.can_view_team_works,
        'can_submit_certificate':   perm.can_submit_certificate,
        'can_view_all_certificates':perm.can_view_all_certificates,
        'can_request_change_order': perm.can_request_change_order,
        'can_view_boq':             perm.can_view_boq,
        'can_view_boq_prices_contractor': perm.can_view_boq_prices_contractor,
    }
