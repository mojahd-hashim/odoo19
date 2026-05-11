from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError
from datetime import date


class MosqueCertificate(models.Model):
    _name = 'mosque.certificate'
    _description = 'Payment Certificate (Istikhlassat)'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'cert_number desc'

    name            = fields.Char(string='Reference', readonly=True, copy=False)
    mosque_id       = fields.Many2one('mosque.mosque', string='Mosque',
                                     required=True, index=True)
    cert_number     = fields.Integer(string='Certificate #', required=True)
    period_from     = fields.Date(string='Period From', required=True)
    period_to       = fields.Date(string='Period To',   required=True)
    submission_date = fields.Date(string='Submission Date', default=fields.Date.today)
    currency_id     = fields.Many2one('res.currency',
                                     default=lambda s: s.env.ref('base.SAR'))

    # ── Lines ─────────────────────────────────────────────────────
    line_ids = fields.One2many('mosque.certificate.line', 'certificate_id',
                               string='BOQ Lines')

    # ── Amounts ───────────────────────────────────────────────────
    certified_amount    = fields.Monetary(string='Certified Amount',
                                          compute='_compute_amounts', store=True,
                                          currency_field='currency_id')
    retention_pct       = fields.Float(string='Retention %', default=10.0)
    retention_amount    = fields.Monetary(string='Retention Amount',
                                          compute='_compute_amounts', store=True,
                                          currency_field='currency_id')
    advance_deduction   = fields.Monetary(string='Advance Deduction',
                                          currency_field='currency_id')
    net_payable         = fields.Monetary(string='Net Payable',
                                          compute='_compute_amounts', store=True,
                                          currency_field='currency_id')

    # ── Approval workflow ─────────────────────────────────────────
    state = fields.Selection([
        ('draft',            'Draft — Contractor'),
        ('consultant_review','Under Consultant Review'),
        ('consultant_approved','Consultant Approved'),
        ('waqf_review',      'Under Waqf Review'),
        ('waqf_approved',    'Waqf Approved — Final'),
        ('paid',             'Paid'),
        ('rejected',         'Rejected'),
    ], string='Status', default='draft', tracking=True, required=True)

    # ── Dates per stage ───────────────────────────────────────────
    consultant_review_date  = fields.Date(string='Consultant Review Date', readonly=True)
    consultant_approved_date= fields.Date(string='Consultant Approval Date', readonly=True)
    waqf_review_date        = fields.Date(string='Waqf Review Date', readonly=True)
    waqf_approved_date      = fields.Date(string='Waqf Approval Date', readonly=True)
    paid_date               = fields.Date(string='Payment Date', readonly=True)

    # ── Reviewers ─────────────────────────────────────────────────
    consultant_reviewer_id = fields.Many2one('res.users', string='Consultant Reviewer',
                                             readonly=True)
    waqf_reviewer_id       = fields.Many2one('res.users', string='Waqf Reviewer',
                                             readonly=True)
    rejection_reason       = fields.Text(string='Rejection Reason')
    notes                  = fields.Text(string='Internal Notes')

    # ── Invoice link ──────────────────────────────────────────────
    invoice_id = fields.Many2one('account.move', string='Vendor Bill', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                mosque = self.env['mosque.mosque'].browse(vals.get('mosque_id'))
                vals['name'] = self.env['ir.sequence'].next_by_code('mosque.certificate') or _('New')
        return super().create(vals_list)

    @api.depends('line_ids.this_period_value', 'retention_pct', 'advance_deduction')
    def _compute_amounts(self):
        for rec in self:
            rec.certified_amount = sum(rec.line_ids.mapped('this_period_value'))
            rec.retention_amount = rec.certified_amount * rec.retention_pct / 100
            rec.net_payable = (rec.certified_amount
                               - rec.retention_amount
                               - rec.advance_deduction)

    # ── Workflow actions ──────────────────────────────────────────
    def action_submit_to_consultant(self):
        for rec in self:
            if not rec.line_ids:
                raise ValidationError(_('Add at least one BOQ line before submitting.'))
            rec.write({
                'state': 'consultant_review',
                'consultant_review_date': date.today(),
            })
            rec.message_post(body=_('Certificate submitted for consultant review.'))

    def action_consultant_approve(self):
        self.write({
            'state': 'consultant_approved',
            'consultant_approved_date': date.today(),
            'consultant_reviewer_id': self.env.user.id,
        })
        self.message_post(body=_('Approved by consultant. Forwarded to Waqf.'))

    def action_submit_to_waqf(self):
        self.write({
            'state': 'waqf_review',
            'waqf_review_date': date.today(),
        })

    def action_waqf_approve(self):
        self.write({
            'state': 'waqf_approved',
            'waqf_approved_date': date.today(),
            'waqf_reviewer_id': self.env.user.id,
        })
        # Update executed quantities on BOQ
        for line in self.line_ids:
            line.boq_id.executed_qty += line.this_period_qty
        self.message_post(body=_('Final Waqf approval granted. Certificate ready for payment.'))

    def action_mark_paid(self):
        self.write({'state': 'paid', 'paid_date': date.today()})

    def action_reject(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('Reject Certificate'),
            'res_model': 'mosque.certificate.reject.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_certificate_id': self.id},
        }

    def action_reset_to_draft(self):
        if self.state in ('paid', 'waqf_approved'):
            raise UserError(_('Cannot reset an approved or paid certificate.'))
        self.write({'state': 'draft'})


class MosqueCertificateLine(models.Model):
    _name = 'mosque.certificate.line'
    _description = 'Certificate BOQ Line'
    _order = 'boq_id'

    certificate_id   = fields.Many2one('mosque.certificate', ondelete='cascade',
                                       required=True, index=True)
    boq_id           = fields.Many2one('mosque.boq', string='BOQ Item',
                                       required=True)
    description      = fields.Text(related='boq_id.description', readonly=True)
    uom              = fields.Selection(related='boq_id.uom', readonly=True)
    unit_price       = fields.Float(related='boq_id.unit_price', readonly=True)
    contracted_qty   = fields.Float(related='boq_id.contracted_qty', readonly=True)
    previous_qty     = fields.Float(string='Previous Certified Qty',
                                    compute='_compute_previous', store=True, digits=(12, 3))
    this_period_qty  = fields.Float(string='This Period Qty', digits=(12, 3))
    cumulative_qty   = fields.Float(string='Cumulative Qty',
                                    compute='_compute_values', store=True, digits=(12, 3))
    this_period_value = fields.Float(string='This Period Value',
                                     compute='_compute_values', store=True, digits=(16, 2))
    cumulative_pct   = fields.Float(string='Cumulative %',
                                    compute='_compute_values', store=True, digits=(5, 2))

    @api.depends('boq_id', 'certificate_id.cert_number')
    def _compute_previous(self):
        for rec in self:
            prev_certs = self.search([
                ('boq_id', '=', rec.boq_id.id),
                ('certificate_id.mosque_id', '=', rec.certificate_id.mosque_id.id),
                ('certificate_id.state', 'in', ['waqf_approved', 'paid']),
                ('certificate_id.cert_number', '<', rec.certificate_id.cert_number),
            ])
            rec.previous_qty = sum(prev_certs.mapped('this_period_qty'))

    @api.depends('previous_qty', 'this_period_qty', 'unit_price', 'contracted_qty')
    def _compute_values(self):
        for rec in self:
            rec.cumulative_qty   = rec.previous_qty + rec.this_period_qty
            rec.this_period_value = rec.this_period_qty * rec.unit_price
            if rec.contracted_qty:
                rec.cumulative_pct = min(100.0,
                    rec.cumulative_qty / rec.contracted_qty * 100)
            else:
                rec.cumulative_pct = 0.0
