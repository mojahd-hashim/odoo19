from odoo import models, fields, api, _

# Standard BOQ items from the contract (69 items)
STANDARD_BOQ_ITEMS = [
    # (item_code, description, uom, contracted_qty, unit_price, category_code)
    # ── ARCHITECTURAL ──────────────────────────────────────────────
    ('ARCH-01', 'Crack Repair — Concrete Plastering', 'm', 160, 38, 'ARCH'),
    ('ARCH-02', 'Parapet Wall Restoration', 'm', 150, 111, 'ARCH'),
    ('ARCH-03', 'Cement Plastering', 'm2', 750, 24, 'ARCH'),
    ('ARCH-04', 'Metal Door Repair & Maintenance', 'm2', 10, 358, 'ARCH'),
    ('ARCH-05', 'Wooden Door Repair & Maintenance', 'm2', 47, 358, 'ARCH'),
    ('ARCH-06', 'Roof Waterproofing System', 'm2', 1050, 168, 'ARCH'),
    ('ARCH-07', 'Window Sealing & Maintenance', 'ls', 1, 8471, 'ARCH'),
    ('ARCH-08', 'HPL Bathroom Doors (Standard)', 'unit', 12, 1693, 'ARCH'),
    ('ARCH-09', 'HPL Bathroom Doors (Accessibility)', 'unit', 2, 2110, 'ARCH'),
    ('ARCH-10', 'CNC Aluminium Strips — Minaret', 'm2', 66, 394, 'ARCH'),
    ('ARCH-11', 'CNC Aluminium Strips — Minaret Top (Blue)', 'm2', 20.5, 281, 'ARCH'),
    ('ARCH-12', 'CNC Aluminium Strips — Entrances & Facades', 'm2', 135.7, 281, 'ARCH'),
    ('ARCH-13', 'Quran Shelf Cabinets', 'unit', 26, 506, 'ARCH'),
    ('ARCH-14', 'Shoe Rack Cabinets', 'unit', 5, 1754, 'ARCH'),
    ('ARCH-15', 'Bench (Seating) — Mosque Interior', 'm', 23.7, 1807, 'ARCH'),
    ('ARCH-16', 'Marble Cladding — Ablution Seats & Sinks', 'm2', 41, 506, 'ARCH'),
    ('ARCH-17', 'Porcelain Tiles — Bathroom Floors', 'm2', 120.6, 179, 'ARCH'),
    ('ARCH-18', 'Porcelain Tiles — Bathroom Walls', 'm2', 405.5, 134, 'ARCH'),
    ('ARCH-19', 'Concrete Ramp — Accessibility (Ablution)', 'm', 35.6, 1015, 'ARCH'),
    ('ARCH-20', 'Granite Cladding — Accessibility Ramp Floor', 'm2', 62.9, 225, 'ARCH'),
    ('ARCH-21', 'Interior Paint — Walls & Ceilings', 'm2', 2440, 23, 'ARCH'),
    ('ARCH-22', 'Natural Stone Cleaning & Sealing (Existing)', 'm2', 679, 21, 'ARCH'),
    ('ARCH-23', 'Aluminium Windows — Double Glazed', 'm2', 20, 563, 'ARCH'),
    ('ARCH-24', 'Accessibility Washbasin', 'unit', 2, 1015, 'ARCH'),
    ('ARCH-25', 'Accessibility Bathroom Fittings (Full Set)', 'unit', 2, 1411, 'ARCH'),
    ('ARCH-26', 'Liquid Soap Dispenser — Ablution Area', 'unit', 18, 1523, 'ARCH'),
    ('ARCH-27', 'Western WC (Toilet Suite)', 'unit', 5, 1523, 'ARCH'),
    ('ARCH-28', 'Eastern WC with Auto-Sensor Flush', 'unit', 8, 3331, 'ARCH'),
    ('ARCH-29', 'Bidet Hose Connection', 'unit', 12, 315, 'ARCH'),
    ('ARCH-30', 'Bathroom Mirror', 'unit', 2, 2371, 'ARCH'),
    ('ARCH-31', 'Paper Towel Holder — Bathrooms', 'unit', 12, 236, 'ARCH'),
    ('ARCH-32', 'Moisture-Resistant Gypsum Board — Ceilings', 'm2', 120.6, 95, 'ARCH'),
    ('ARCH-33', 'Ablution Basin (Wudhu Sink)', 'unit', 7, 903, 'ARCH'),
    ('ARCH-34', 'Decorative Acrylic Wall — Ablution (Branded)', 'm2', 18, 903, 'ARCH'),
    ('ARCH-35', 'Clothes Hanger — Stainless Steel', 'unit', 27, 77, 'ARCH'),
    ('ARCH-36', 'Concrete Block Seating Platforms — Ablution', 'm3', 6.05, 225, 'ARCH'),
    ('ARCH-37', 'Demolition Works — Bathroom Partitions', 'm3', 9.8, 225, 'ARCH'),
    ('ARCH-38', 'Blockwork Construction', 'm3', 13.8, 225, 'ARCH'),
    ('ARCH-39', 'Waterproofing — Bathrooms & Ablution Areas', 'm2', 110, 72, 'ARCH'),
    ('ARCH-40', 'Handrail — Stainless Steel SS304', 'm', 23, 394, 'ARCH'),
    ('ARCH-61', 'Exterior Paint — Building Facades', 'm2', 1197, 38, 'ARCH'),
    ('ARCH-64', 'Partition Repainting', 'm2', 90, 360, 'ARCH'),
    ('ARCH-65', 'Natural Stone Cladding — Facades', 'm2', 250, 280, 'ARCH'),
    # ── MECHANICAL ─────────────────────────────────────────────────
    ('MECH-41', 'Re-fixing Package AC Units on Anti-Vibration Mounts', 'unit', 5, 1693, 'MECH'),
    ('MECH-42', 'Fibreglass Insulation — Roof Pipework', 'm', 40, 168, 'MECH'),
    ('MECH-43', 'Water Pipeline Flushing & Tank Cleaning', 'ls', 1, 13554, 'MECH'),
    ('MECH-44', 'Concrete Base — Roof Water Tanks', 'unit', 3, 4517, 'MECH'),
    ('MECH-45', 'Floor Drain — UPVC', 'unit', 7, 281, 'MECH'),
    ('MECH-46', 'Linear Drainage Channel — Ablution Area', 'm', 18.81, 2032, 'MECH'),
    ('MECH-47', 'Exhaust Fan — Ceiling Mounted 12"x12"', 'unit', 5, 846, 'MECH'),
    ('MECH-48', 'Exhaust Fan — Ceiling Mounted 6"x6"', 'unit', 8, 846, 'MECH'),
    ('MECH-49', 'Wall-Mounted Extract Fan 50x50cm', 'unit', 4, 1241, 'MECH'),
    ('MECH-50', 'Sensor-Operated Wall Wudhu Mixer (Laser)', 'unit', 15, 3500, 'MECH'),
    ('MECH-51', 'Sensor-Operated Basin Mixer (Laser)', 'unit', 8, 2371, 'MECH'),
    ('MECH-66', 'Plumbing Rough-In — Complete (Lump Sum)', 'ls', 1, 20000, 'MECH'),
    ('MECH-68', 'HVAC Side Wall Grille', 'm', 65, 293, 'MECH'),
    ('MECH-69', 'Linear Slot Diffuser', 'm', 120, 293, 'MECH'),
    # ── ELECTRICAL ─────────────────────────────────────────────────
    ('ELEC-52', 'Main DB — Cable Numbering & Testing', 'ls', 1, 2823, 'ELEC'),
    ('ELEC-53', 'Main DB — Load Balance Schedule', 'unit', 1, 7567, 'ELEC'),
    ('ELEC-54', 'Sub DB — Cable Numbering', 'unit', 3, 789, 'ELEC'),
    ('ELEC-55', 'Sub DB — Load Balance Schedule', 'unit', 3, 1355, 'ELEC'),
    ('ELEC-56', 'Isolator Switch — Mechanical Equipment 32A', 'unit', 2, 474, 'ELEC'),
    ('ELEC-57', 'Cable Trunking, Fixing & Protection (Complete)', 'ls', 1, 58682, 'ELEC'),
    ('ELEC-58', 'CNC LED Strip Lighting', 'm', 247, 48, 'ELEC'),
    ('ELEC-59', 'Electric Hand Dryer — Stainless Steel', 'unit', 2, 1693, 'ELEC'),
    ('ELEC-60', 'Auto-Sensor Paper Dispenser (Laser)', 'unit', 2, 1580, 'ELEC'),
    ('ELEC-62', 'LED Light Fittings (Replacement)', 'unit', 300, 300, 'ELEC'),
    ('ELEC-63', 'Sockets & Switches (Replacement)', 'unit', 50, 44, 'ELEC'),
    ('ELEC-67', 'Electrical Rough-In — Complete (Lump Sum)', 'ls', 1, 7000, 'ELEC'),
]


class LoadBOQWizard(models.TransientModel):
    _name = 'mosque.boq.load.wizard'
    _description = 'Load Standard BOQ Template'

    mosque_ids = fields.Many2many('mosque.mosque', string='Mosques',
                                  domain=[('state', 'in', ['draft', 'mobilizing'])])
    overwrite_existing = fields.Boolean(string='Overwrite Existing Lines', default=False)
    note = fields.Char(string='Note',
                       default='This will load all 69 standard BOQ items from the contract.')

    def action_load(self):
        BOQ = self.env['mosque.boq']
        Cat = self.env['mosque.boq.category']

        cat_map = {
            'ARCH': Cat.search([('code', '=', 'ARCH')], limit=1),
            'MECH': Cat.search([('code', '=', 'MECH')], limit=1),
            'ELEC': Cat.search([('code', '=', 'ELEC')], limit=1),
        }

        for mosque in self.mosque_ids:
            if self.overwrite_existing:
                BOQ.search([('mosque_id', '=', mosque.id)]).unlink()

            existing_codes = BOQ.search([('mosque_id', '=', mosque.id)]).mapped('item_code')

            for (code, desc, uom, qty, price, cat) in STANDARD_BOQ_ITEMS:
                if code not in existing_codes:
                    BOQ.create({
                        'mosque_id':      mosque.id,
                        'category_id':    cat_map[cat].id,
                        'item_code':      code,
                        'description':    desc,
                        'uom':            uom,
                        'contracted_qty': qty,
                        'unit_price':     price,
                    })

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('BOQ Loaded'),
                'message': _('Standard BOQ template loaded for %d mosque(s).')
                           % len(self.mosque_ids),
                'type': 'success',
                'sticky': False,
            }
        }
