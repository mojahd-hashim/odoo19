from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class MosqueBOQCategory(models.Model):
    _name = 'mosque.boq.category'
    _description = 'BOQ Work Category'
    _order = 'sequence'

    name = fields.Char(string='Category Name', required=True, translate=True)
    code = fields.Char(string='Code')
    sequence = fields.Integer(default=10)
    color = fields.Integer()
    type = fields.Selection([
        ('architectural', 'Architectural & Structural'),
        ('mechanical',    'Mechanical'),
        ('electrical',    'Electrical'),
    ], string='Type', required=True)


class MosqueBOQ(models.Model):
    _name = 'mosque.boq'
    _description = 'Bill of Quantities Line'
    _inherit = ['mail.thread']
    _order = 'mosque_id, category_id, sequence'

    mosque_id    = fields.Many2one('mosque.mosque', string='Mosque',
                                   required=True, ondelete='cascade', index=True)
    category_id  = fields.Many2one('mosque.boq.category', string='Category',
                                   required=True)
    work_type    = fields.Selection(related='category_id.type', store=True)
    sequence     = fields.Integer(default=10)

    item_code    = fields.Char(string='Item Code')
    description  = fields.Text(string='Description', required=True, translate=True)
    uom          = fields.Selection([
        ('m',    'Linear Meter (m)'),
        ('m2',   'Square Meter (m²)'),
        ('m3',   'Cubic Meter (m³)'),
        ('unit', 'Unit (No.)'),
        ('ls',   'Lump Sum'),
    ], string='UOM', required=True, default='m2')

    contracted_qty  = fields.Float(string='Contracted Qty', digits=(12, 3))
    unit_price      = fields.Float(string='Unit Price (SAR)', digits=(12, 2))
    contracted_value = fields.Float(string='Contracted Value',
                                    compute='_compute_values', store=True, digits=(16, 2))

    executed_qty    = fields.Float(string='Executed Qty', digits=(12, 3), tracking=True)
    execution_pct   = fields.Float(string='Execution %',
                                   compute='_compute_values', store=True, digits=(5, 2))
    executed_value  = fields.Float(string='Executed Value',
                                   compute='_compute_values', store=True, digits=(16, 2))

    # Certificate lines reference
    cert_line_ids = fields.One2many('mosque.certificate.line', 'boq_id',
                                    string='Certificate Lines')
    certified_qty = fields.Float(string='Certified Qty',
                                 compute='_compute_certified', store=True, digits=(12, 3))
    remaining_qty = fields.Float(string='Remaining Qty',
                                 compute='_compute_certified', store=True, digits=(12, 3))

    notes = fields.Text(string='Notes')
    is_variation = fields.Boolean(string='Variation Item', default=False)
    change_order_id = fields.Many2one('mosque.change.order', string='Change Order Ref.')

    @api.depends('contracted_qty', 'unit_price', 'executed_qty')
    def _compute_values(self):
        for rec in self:
            rec.contracted_value = rec.contracted_qty * rec.unit_price
            rec.executed_value   = rec.executed_qty   * rec.unit_price
            if rec.contracted_qty:
                rec.execution_pct = min(100.0, rec.executed_qty / rec.contracted_qty * 100)
            else:
                rec.execution_pct = 0.0

    @api.depends('cert_line_ids.this_period_qty', 'cert_line_ids.certificate_id.state')
    def _compute_certified(self):
        for rec in self:
            approved_lines = rec.cert_line_ids.filtered(
                lambda l: l.certificate_id.state == 'waqf_approved')
            rec.certified_qty  = sum(approved_lines.mapped('this_period_qty'))
            rec.remaining_qty  = max(0.0, rec.contracted_qty - rec.certified_qty)

    @api.constrains('executed_qty', 'contracted_qty')
    def _check_executed_qty(self):
        for rec in self:
            if not rec.is_variation and rec.executed_qty > rec.contracted_qty * 1.1:
                raise ValidationError(
                    _('Executed qty cannot exceed 110%% of contracted qty for item: %s\n'
                      'Please raise a Change Order for extra quantities.') % rec.description)

    # ── Dashboard summary per mosque ──────────────────────────────
    @api.model
    def get_boq_summary(self, mosque_id):
        lines = self.search([('mosque_id', '=', mosque_id)])
        by_category = {}
        for line in lines:
            cat = line.category_id.name
            if cat not in by_category:
                by_category[cat] = {
                    'type': line.work_type,
                    'contracted': 0.0,
                    'executed': 0.0,
                    'pct': 0.0,
                }
            by_category[cat]['contracted'] += line.contracted_value
            by_category[cat]['executed']   += line.executed_value

        for cat in by_category:
            c = by_category[cat]['contracted']
            e = by_category[cat]['executed']
            by_category[cat]['pct'] = round(e / c * 100, 1) if c else 0.0

        return {
            'total_contracted': sum(l.contracted_value for l in lines),
            'total_executed':   sum(l.executed_value   for l in lines),
            'categories': by_category,
            'items_count': len(lines),
        }
