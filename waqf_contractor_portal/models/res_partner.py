from odoo import models, fields, api, _


class ResPartnerContractor(models.Model):
    """Extend res.partner to mark contractor supervisors."""
    _inherit = 'res.partner'

    contractor_supervisor = fields.Boolean(
        string='Contractor Supervisor',
        default=False,
        help='Mark this contact as a contractor site supervisor '
             'to appear in the Waqf contractor portal.',
    )
    assigned_mosque_id = fields.Many2one(
        'mosque.mosque',
        string='Assigned Mosque',
        help='Primary mosque this supervisor is responsible for.',
    )
    contractor_company = fields.Char(string='Contractor Company')

    def _get_portal_return_url(self):
        return '/contractor'
