from odoo import models, fields, api, _


class MosqueMosqueDemo(models.Model):
    """Add is_demo flag to mosque — demo records excluded from reports."""
    _inherit = 'mosque.mosque'

    is_demo = fields.Boolean(
        string='Demo Record',
        default=False,
        help='If checked, this mosque is a demo record and will be '
             'excluded from production reports and KPI dashboards.',
    )


class ContractorWorkLogDemo(models.Model):
    _inherit = 'contractor.work.log'

    is_demo = fields.Boolean(string='Demo Record', default=False)


class MosqueCertificateDemo(models.Model):
    _inherit = 'mosque.certificate'

    is_demo = fields.Boolean(string='Demo Record', default=False)


class MosqueChangeOrderDemo(models.Model):
    _inherit = 'mosque.change.order'

    is_demo = fields.Boolean(string='Demo Record', default=False)
