from odoo import models, fields, api, _


class HrEmployeeMobile(models.Model):
    _inherit = 'hr.employee'

    # Mobile app tokens
    api_token_ids = fields.One2many(
        'waqf.api.token', 'employee_id',
        string='API Tokens',
    )
    active_token_count = fields.Integer(
        compute='_compute_token_count',
        string='Active Tokens',
    )

    # Assigned mosques for consultant
    assigned_mosque_ids = fields.Many2many(
        'mosque.mosque',
        'hr_employee_mosque_rel',
        'employee_id', 'mosque_id',
        string='Assigned Mosques',
        help='Mosques this consultant is responsible for supervising.',
    )
    mosque_package_ids = fields.Many2many(
        'mosque.package',
        'hr_employee_package_rel',
        'employee_id', 'package_id',
        string='Assigned Packages',
        help='Geographic packages — assigns all mosques in package.',
    )

    # Computed: all mosques (direct + via packages)
    all_mosque_ids = fields.Many2many(
        'mosque.mosque',
        compute='_compute_all_mosques',
        string='All Assigned Mosques',
    )

    # FCM push token (updated by app)
    fcm_token = fields.Char(
        string='FCM Push Token', copy=False,
        help='Firebase push notification token — updated by mobile app.',
    )

    @api.depends('api_token_ids', 'api_token_ids.is_active')
    def _compute_token_count(self):
        for emp in self:
            emp.active_token_count = len(
                emp.api_token_ids.filtered(lambda t: t.is_active))

    @api.depends('assigned_mosque_ids', 'mosque_package_ids',
                 'mosque_package_ids.mosque_ids')
    def _compute_all_mosques(self):
        for emp in self:
            direct   = emp.assigned_mosque_ids
            via_pkg  = emp.mosque_package_ids.mapped('mosque_ids')
            emp.all_mosque_ids = direct | via_pkg

    def action_generate_api_token(self):
        self.ensure_one()
        raw, token_id = self.env['waqf.api.token'].generate_token(
            self.id, 'Mobile App Token')
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'waqf.token.show.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_token_id': token_id,
                'default_raw_token': raw,
            },
        }
