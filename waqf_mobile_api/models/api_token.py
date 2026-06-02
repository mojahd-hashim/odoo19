from odoo import models, fields, api, _
from odoo.exceptions import AccessError
import secrets
import hashlib
from datetime import datetime, timedelta


class WaqfApiToken(models.Model):
    """
    Per-employee API tokens for mobile app authentication.
    Tokens are hashed before storage — raw token shown once on creation.
    """
    _name = 'waqf.api.token'
    _description = 'Mobile App API Token'
    _order = 'create_date desc'

    name        = fields.Char(string='Token Name', required=True,
                              default='Mobile App Token')
    employee_id = fields.Many2one('hr.employee', string='Employee',
                                  required=True, ondelete='cascade', index=True)
    user_id     = fields.Many2one(related='employee_id.user_id',
                                  string='User', store=True)

    token_hash  = fields.Char(string='Token Hash', readonly=True, copy=False)
    token_prefix = fields.Char(string='Token Preview', readonly=True,
                               help='First 8 chars — for identification only')

    is_active   = fields.Boolean(string='Active', default=True)
    last_used   = fields.Datetime(string='Last Used', readonly=True)
    expires_at  = fields.Datetime(string='Expires At')
    device_info = fields.Char(string='Device Info')
    fcm_token   = fields.Char(string='FCM Push Token',
                               help='Firebase Cloud Messaging token for push notifications')

    is_expired  = fields.Boolean(compute='_compute_is_expired', store=True)

    @api.depends('expires_at')
    def _compute_is_expired(self):
        now = datetime.now()
        for rec in self:
            rec.is_expired = bool(rec.expires_at and rec.expires_at < now)

    def _hash_token(self, raw_token):
        return hashlib.sha256(raw_token.encode()).hexdigest()

    @api.model
    def generate_token(self, employee_id, name='Mobile App', expires_days=365):
        """Generate a new token — returns raw token ONCE."""
        raw = 'waqf_' + secrets.token_urlsafe(32)
        expires = datetime.now() + timedelta(days=expires_days)

        record = self.create({
            'name':         name,
            'employee_id':  employee_id,
            'token_hash':   self._hash_token(raw),
            'token_prefix': raw[:8],
            'expires_at':   expires,
            'is_active':    True,
        })
        return raw, record.id

    @api.model
    def authenticate(self, raw_token):
        """
        Validate token — returns employee record or False.
        Updates last_used timestamp.
        """
        if not raw_token or not raw_token.startswith('waqf_'):
            return False

        token_hash = self._hash_token(raw_token)
        token = self.sudo().search([
            ('token_hash', '=', token_hash),
            ('is_active',  '=', True),
            ('is_expired', '=', False),
        ], limit=1)

        if not token:
            return False

        if not token.last_used or (
                fields.Datetime.now() - token.last_used
        ).total_seconds() > 300:
            token.sudo().write({
                'last_used': fields.Datetime.now()
            })
        return token.employee_id

    def action_revoke(self):
        self.write({'is_active': False})

    def action_generate_new(self):
        """Revoke current and generate new token."""
        self.write({'is_active': False})
        raw, new_id = self.generate_token(
            self.employee_id.id, self.name)
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'waqf.token.show.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_token_id': new_id,
                'default_raw_token': raw,
            },
        }


class WaqfTokenShowWizard(models.TransientModel):
    """Show raw token once after generation."""
    _name = 'waqf.token.show.wizard'
    _description = 'Show Generated Token'

    token_id  = fields.Many2one('waqf.api.token')
    raw_token = fields.Char(string='API Token', readonly=True)

    def action_copy_done(self):
        return {'type': 'ir.actions.act_window_close'}
