from odoo import models, fields, api, _


class RejectCertificateWizard(models.TransientModel):
    _name = 'mosque.certificate.reject.wizard'
    _description = 'Reject Certificate Wizard'

    certificate_id = fields.Many2one('mosque.certificate', required=True)
    reason = fields.Text(string='Rejection Reason', required=True)

    def action_confirm_reject(self):
        self.certificate_id.write({
            'state': 'rejected',
            'rejection_reason': self.reason,
        })
        self.certificate_id.message_post(
            body=_('Certificate rejected. Reason: %s') % self.reason)
        return {'type': 'ir.actions.act_window_close'}
