from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import date, timedelta
import logging

_logger = logging.getLogger(__name__)

# ── Demo BOQ items (subset of 20 representative items) ────────────────────
DEMO_BOQ = [
    # (code, description, uom, contracted_qty, unit_price, category)
    ('ARCH-01', 'إصلاح تشققات — الجدران الداخلية',       'm',   160.0, 38.0,   'ARCH'),
    ('ARCH-02', 'ترميم السترة — الحواف الخارجية',         'm',   150.0, 111.0,  'ARCH'),
    ('ARCH-03', 'لياسة إسمنتية — الجدران',               'm2',  750.0, 24.0,   'ARCH'),
    ('ARCH-04', 'إصلاح وصيانة الأبواب المعدنية',         'm2',   10.0, 358.0,  'ARCH'),
    ('ARCH-05', 'إصلاح وصيانة الأبواب الخشبية',         'm2',   47.0, 358.0,  'ARCH'),
    ('ARCH-06', 'عزل مائي للأسطح',                       'm2', 1050.0, 168.0,  'ARCH'),
    ('ARCH-17', 'بلاط بورسلان — أرضيات دورات المياه',   'm2',  120.6, 179.0,  'ARCH'),
    ('ARCH-21', 'دهان داخلي — الجدران والأسقف',         'm2', 2440.0,  23.0,  'ARCH'),
    ('ARCH-33', 'حوض وضوء مع خلاط',                     'unit',  7.0, 903.0,  'ARCH'),
    ('ARCH-40', 'درابزين استينلس ستيل',                  'm',    23.0, 394.0,  'ARCH'),
    ('ARCH-61', 'دهان خارجي — الواجهات',                'm2', 1197.0,  38.0,  'ARCH'),
    ('MECH-41', 'إعادة تركيب وحدات التكييف',            'unit',  5.0,1693.0,  'MECH'),
    ('MECH-43', 'تنظيف خزانات المياه وشبكة التغذية',   'ls',    1.0,13554.0, 'MECH'),
    ('MECH-47', 'مروحة شفط سقفية 12×12',               'unit',  5.0, 846.0,  'MECH'),
    ('MECH-50', 'خلاط وضوء بالسنسور',                   'unit', 15.0,3500.0,  'MECH'),
    ('ELEC-52', 'لوحة كهربائية رئيسية — ترقيم الأسلاك','ls',    1.0,2823.0,  'ELEC'),
    ('ELEC-57', 'مسارات كابلات كاملة',                  'ls',    1.0,58682.0, 'ELEC'),
    ('ELEC-58', 'إضاءة CNC LED',                        'm',   247.0,  48.0,  'ELEC'),
    ('ELEC-62', 'تغيير أجهزة إضاءة LED',               'unit', 300.0, 300.0,  'ELEC'),
    ('ELEC-63', 'تغيير مفاتيح وأقابس كهربائية',        'unit',  50.0,  44.0,  'ELEC'),
]

# ── Demo tasks with subtasks ──────────────────────────────────────────────
DEMO_TASKS = [
    {
        'name': 'مراجعة واعتماد رسومات MEP',
        'stage': 'consultant_review',
        'review_state': 'approved',   # main task green — all subtasks done
        'days_offset': -45,
        'subtasks': [
            {'name': 'رسومات الكهرباء — الطابق الأرضي',  'review_state': 'approved'},
            {'name': 'رسومات التكييف والتهوية',           'review_state': 'approved'},
            {'name': 'رسومات الصرف الصحي',               'review_state': 'approved'},
        ],
    },
    {
        'name': 'أعمال التشطيبات الداخلية',
        'stage': 'in_progress',
        'review_state': 'rejected',   # red — one subtask rejected
        'days_offset': -30,
        'subtasks': [
            {'name': 'دهان داخلي — الجناح الشمالي',      'review_state': 'approved'},
            {'name': 'تغيير باب خشبي — المدخل الخلفي',   'review_state': 'rejected',
             'rejection_note': 'الصورة لا تُظهر الإطار الكامل للباب الجديد — أعد التصوير'},
            {'name': 'لياسة إسمنتية — الجدار الغربي',    'review_state': 'pending'},
        ],
    },
    {
        'name': 'أعمال الكهرباء الرئيسية',
        'stage': 'in_progress',
        'review_state': 'blocked',    # yellow — CO pending
        'days_offset': -20,
        'has_co': True,
        'subtasks': [
            {'name': 'تركيب لوحة كهربائية رئيسية',       'review_state': 'approved'},
            {'name': 'مسارات كابلات الطابق الأول',        'review_state': 'blocked'},
            {'name': 'إضاءة CNC LED — الصالة الرئيسية',  'review_state': 'pending'},
        ],
    },
    {
        'name': 'أعمال دورات المياه والوضوء',
        'stage': 'todo',
        'review_state': 'pending',    # grey — not started
        'days_offset': 10,
        'subtasks': [
            {'name': 'تركيب أحواض وضوء بالسنسور',        'review_state': 'pending'},
            {'name': 'بلاط بورسلان — أرضيات دورات المياه', 'review_state': 'pending'},
            {'name': 'تركيب مروحة شفط',                  'review_state': 'pending'},
        ],
    },
    {
        'name': 'تقرير الجودة والسلامة الأسبوعي',
        'stage': 'todo',
        'review_state': 'pending',    # grey — overdue
        'days_offset': -5,            # overdue
        'subtasks': [],
    },
]

# ── Demo work logs ────────────────────────────────────────────────────────
DEMO_WORK_LOGS = [
    {
        'name': 'تغيير باب خشبي — المدخل الخلفي',
        'boq_code': 'ARCH-05', 'qty': 2.1,
        'state': 'rejected',
        'reject_reason': 'الصورة لا تُظهر الإطار الكامل للباب الجديد',
        'days_ago': 3,
    },
    {
        'name': 'دهان داخلي — الجناح الشمالي',
        'boq_code': 'ARCH-21', 'qty': 120.0,
        'state': 'approved',
        'days_ago': 7,
    },
    {
        'name': 'إصلاح تشققات — الجدار الشرقي',
        'boq_code': 'ARCH-01', 'qty': 45.0,
        'state': 'approved',
        'days_ago': 10,
    },
    {
        'name': 'تنظيف خزانات المياه',
        'boq_code': 'MECH-43', 'qty': 1.0,
        'state': 'submitted',
        'days_ago': 1,
    },
    {
        'name': 'تركيب لوحة كهربائية رئيسية',
        'boq_code': 'ELEC-52', 'qty': 1.0,
        'state': 'approved',
        'days_ago': 14,
    },
]


class DemoSetupWizard(models.TransientModel):
    _name = 'waqf.demo.setup.wizard'
    _description = 'Demo Environment Setup Wizard'

    state         = fields.Selection([
        ('ready', 'Ready'),
        ('done',  'Done'),
        ('error', 'Error'),
    ], default='ready')
    result_log    = fields.Text(string='Setup Log', readonly=True)
    demo_mosque_id = fields.Many2one(
        'mosque.mosque', string='Demo Mosque', readonly=True)
    already_exists = fields.Boolean(
        compute='_compute_already_exists')

    @api.depends()
    def _compute_already_exists(self):
        for rec in self:
            rec.already_exists = bool(
                self.env['mosque.mosque'].search(
                    [('code', '=', 'DEMO-01')], limit=1))

    # ══════════════════════════════════════════════════════════════
    # MAIN SETUP
    # ══════════════════════════════════════════════════════════════
    def action_setup_demo(self):
        log = []
        try:
            # 1. Clean existing demo data
            self._cleanup_demo()
            log.append('✓ تم حذف البيانات التجريبية السابقة')

            # 2. Create demo package
            package = self._create_demo_package()
            log.append('✓ تم إنشاء الحزمة التجريبية')

            # 3. Create demo mosque
            mosque = self._create_demo_mosque(package)
            log.append('✓ تم إنشاء المسجد التجريبي: %s' % mosque.name)

            # 4. Load BOQ
            boq_map = self._create_demo_boq(mosque)
            log.append('✓ تم تحميل %d بند في جدول الكميات' % len(boq_map))

            # 5. Create Odoo project + stages
            project = self._create_demo_project(mosque)
            log.append('✓ تم إنشاء مشروع أودو: %s' % project.name)

            # 6. Create tasks + subtasks
            tasks = self._create_demo_tasks(project, mosque)
            log.append('✓ تم إنشاء %d مهمة رئيسية مع مهام فرعية' % len(tasks))

            # 7. Create change order
            co = self._create_demo_co(mosque)
            log.append('✓ تم إنشاء أمر تغيير: %s' % co.name)

            # 8. Link CO to blocked task
            self._link_co_to_task(tasks, co)
            log.append('✓ تم ربط أمر التغيير بالمهمة المجمّدة')

            # 9. Create work logs
            logs_count = self._create_demo_work_logs(mosque, boq_map)
            log.append('✓ تم إنشاء %d سجل عمل ميداني' % logs_count)

            # 10. Create certificate
            cert = self._create_demo_certificate(mosque, boq_map)
            log.append('✓ تم إنشاء مستخلص تجريبي: %s' % cert.name)

            log.append('')
            log.append('═' * 40)
            log.append('البيئة التجريبية جاهزة للاستخدام')
            log.append('المسجد: %s' % mosque.name)
            log.append('رابط المشروع: Project → [DEMO-01]')

            self.write({
                'state': 'done',
                'result_log': '\n'.join(log),
                'demo_mosque_id': mosque.id,
            })

        except Exception as e:
            _logger.exception('Demo setup failed')
            self.write({
                'state': 'error',
                'result_log': '\n'.join(log) + '\n\n❌ خطأ: %s' % str(e),
            })

        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_reset_demo(self):
        """Wipe and recreate all demo data."""
        self.write({'state': 'ready', 'result_log': False})
        return self.action_setup_demo()

    def action_open_mosque(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mosque.mosque',
            'res_id': self.demo_mosque_id.id,
            'view_mode': 'form',
        }

    def action_open_project(self):
        mosque = self.demo_mosque_id
        if mosque and mosque.project_id:
            return {
                'type': 'ir.actions.act_window',
                'res_model': 'project.project',
                'res_id': mosque.project_id.id,
                'view_mode': 'form',
            }

    # ══════════════════════════════════════════════════════════════
    # CLEANUP
    # ══════════════════════════════════════════════════════════════
    def _cleanup_demo(self):
        env = self.env

        # Work logs
        env['contractor.work.log'].sudo().search(
            [('is_demo', '=', True)]).unlink()

        # Certificates
        env['mosque.certificate'].sudo().search(
            [('is_demo', '=', True)]).unlink()

        # Change orders
        env['mosque.change.order'].sudo().search(
            [('is_demo', '=', True)]).unlink()

        # Mosque + cascade (BOQ, supervision, attendance)
        demo_mosques = env['mosque.mosque'].sudo().search(
            [('is_demo', '=', True)])
        for m in demo_mosques:
            if m.project_id:
                m.project_id.sudo().unlink()
        demo_mosques.sudo().unlink()

        # Package
        env['mosque.package'].sudo().search(
            [('code', '=', 'DEMO-PKG')]).unlink()

    # ══════════════════════════════════════════════════════════════
    # CREATORS
    # ══════════════════════════════════════════════════════════════
    def _create_demo_package(self):
        return self.env['mosque.package'].sudo().create({
            'name':          'Demo Package — بيئة تجريبية',
            'code':          'DEMO-PKG',
            'phase':         '1',
            'sequence':      99,
            'planned_start': date.today(),
            'planned_end':   date.today() + timedelta(days=120),
            'color':         10,
        })

    def _create_demo_mosque(self, package):
        today = date.today()
        return self.env['mosque.mosque'].sudo().create({
            'name':          '[DEMO] جامع تجريبي — الملقا',
            'code':          'DEMO-01',
            'package_id':    package.id,
            'city':          'riyadh',
            'district':      'الملقا',
            'latitude':      24.7136,
            'longitude':     46.6753,
            'geofence_radius': 100,
            'contract_value':  1_357_488.0,
            'planned_start': today - timedelta(days=60),
            'planned_end':   today + timedelta(days=60),
            'actual_start':  today - timedelta(days=55),
            'contractor':    'شركة البناء الذهبي للمقاولات [DEMO]',
            'state':         'active',
            'is_demo':       True,
            'notes':         'بيئة تجريبية — هذه البيانات وهمية لأغراض العرض والتدريب فقط',
        })

    def _create_demo_boq(self, mosque):
        BOQ   = self.env['mosque.boq'].sudo()
        Cat   = self.env['mosque.boq.category'].sudo()
        boq_map = {}  # code → boq record

        cat_cache = {}
        for (code, desc, uom, qty, price, cat_code) in DEMO_BOQ:
            if cat_code not in cat_cache:
                cat = Cat.search([('code', '=', cat_code)], limit=1)
                if not cat:
                    type_map = {
                        'ARCH': 'architectural',
                        'MECH': 'mechanical',
                        'ELEC': 'electrical',
                    }
                    name_map = {
                        'ARCH': 'Architectural & Structural Works',
                        'MECH': 'Mechanical Works',
                        'ELEC': 'Electrical Works',
                    }
                    cat = Cat.create({
                        'code': cat_code,
                        'name': name_map[cat_code],
                        'type': type_map[cat_code],
                    })
                cat_cache[cat_code] = cat

            boq = BOQ.create({
                'mosque_id':      mosque.id,
                'category_id':    cat_cache[cat_code].id,
                'item_code':      code,
                'description':    desc,
                'uom':            uom,
                'contracted_qty': qty,
                'unit_price':     price,
                'executed_qty':   round(qty * 0.35, 2),  # 35% executed
            })
            boq_map[code] = boq

        return boq_map

    def _create_demo_project(self, mosque):
        Project = self.env['project.project'].sudo()
        project = Project.create({
            'name':       '[DEMO-01] جامع تجريبي — الملقا',
            'date_start': mosque.planned_start,
            'date':       mosque.planned_end,
            'description': 'مشروع تجريبي — للعرض والتدريب فقط',
        })
        mosque.sudo().write({'project_id': project.id})
        return project

    def _get_stage(self, waqf_stage_key, project):
        """Get or create a task stage."""
        Stage = self.env['project.task.type'].sudo()
        stage = Stage.search([
            ('waqf_stage', '=', waqf_stage_key),
            '|', ('project_ids', 'in', project.id),
                 ('project_ids', '=', False),
        ], limit=1)

        if not stage:
            # Fallback names
            name_map = {
                'todo':              'To Do',
                'in_progress':       'In Progress',
                'consultant_review': 'Consultant Review',
                'waqf_approval':     'Waqf Approval',
                'done':              'Done',
            }
            stage = Stage.create({
                'name':        name_map.get(waqf_stage_key, waqf_stage_key),
                'waqf_stage':  waqf_stage_key,
                'project_ids': [(4, project.id)],
                'require_green': waqf_stage_key == 'waqf_approval',
            })
        else:
            stage.sudo().write({'project_ids': [(4, project.id)]})

        return stage

    def _create_demo_tasks(self, project, mosque):
        Task  = self.env['project.task'].sudo()
        today = date.today()
        created_tasks = []

        for tmpl in DEMO_TASKS:
            stage = self._get_stage(tmpl['stage'], project)
            deadline = today + timedelta(days=tmpl['days_offset'])

            # Create main task — bypass stage guard
            main = Task.with_context(bypass_stage_guard=True).create({
                'name':         tmpl['name'],
                'project_id':   project.id,
                'stage_id':     stage.id,
                'review_state': tmpl['review_state'],
                'date_deadline': deadline,
            })

            # Create subtasks
            for sub_tmpl in tmpl.get('subtasks', []):
                sub_stage = self._get_stage('in_progress', project)
                if sub_tmpl['review_state'] == 'approved':
                    sub_stage = self._get_stage('consultant_review', project)

                subtask = Task.with_context(bypass_stage_guard=True).create({
                    'name':           sub_tmpl['name'],
                    'project_id':     project.id,
                    'parent_id':      main.id,
                    'stage_id':       sub_stage.id,
                    'review_state':   sub_tmpl['review_state'],
                    'rejection_note': sub_tmpl.get('rejection_note', False),
                })

                if sub_tmpl['review_state'] == 'rejected':
                    subtask.message_post(
                        body=_('❌ رفض الاستشاري هذه المهمة الفرعية.<br/>'
                               '<b>السبب:</b> %s') % sub_tmpl.get(
                            'rejection_note', ''))

                elif sub_tmpl['review_state'] == 'approved':
                    subtask.write({
                        'approved_by':   self.env.user.id,
                        'approved_date': today - timedelta(days=5),
                    })

            # Chatter messages for realism
            if tmpl['review_state'] == 'approved':
                main.message_post(
                    body=_('✅ جميع المهام الفرعية معتمدة — '
                           'المهمة جاهزة لاعتماد الوقف.'))
            elif tmpl['review_state'] == 'rejected':
                main.message_post(
                    body=_('❌ يوجد مهمة فرعية مرفوضة — '
                           'يجب تصحيحها قبل الانتقال للمرحلة التالية.'))
            elif tmpl['review_state'] == 'blocked':
                main.message_post(
                    body=_('🔒 المهمة مجمّدة بانتظار اعتماد أمر التغيير.'))

            created_tasks.append(main)

        return created_tasks

    def _create_demo_co(self, mosque):
        CO = self.env['mosque.change.order'].sudo()
        return CO.create({
            'mosque_id':      mosque.id,
            'type':           'cost',
            'reason':         'تبيّن أثناء تنفيذ مسارات الكابلات أن الكميات الفعلية '
                              'تتجاوز التعاقدية بنسبة 18% بسبب تعديل موقع اللوحة '
                              'الكهربائية الرئيسية. يُطلب زيادة كمية بند ELEC-57 '
                              'من 1 LS إلى LS+18% مع تعديل السعر الإجمالي.',
            'amount':         10_561.76,
            'days_extension': 5,
            'state':          'review',
            'is_demo':        True,
        })

    def _link_co_to_task(self, tasks, co):
        """Link CO to the blocked task and its blocked subtasks."""
        Task = self.env['project.task'].sudo()
        for task in tasks:
            if task.review_state == 'blocked':
                task.write({
                    'blocking_co_id': co.id,
                    'review_state':   'blocked',
                })
                # Also block subtasks
                for sub in task.child_ids:
                    if sub.review_state == 'blocked':
                        sub.write({'blocking_co_id': co.id})

    def _create_demo_work_logs(self, mosque, boq_map):
        WorkLog    = self.env['contractor.work.log'].sudo()
        Partner    = self.env['res.partner'].sudo()
        today      = date.today()

        # Get or create demo supervisor partner
        supervisor = Partner.search(
            [('name', 'ilike', 'DEMO Supervisor')], limit=1)
        if not supervisor:
            supervisor = Partner.create({
                'name':                  'DEMO Supervisor — مشرف تجريبي',
                'email':                 'demo.supervisor@demo.kawaqf.org',
                'phone':                 '+966500000001',
                'contractor_supervisor': True,
                'assigned_mosque_id':    mosque.id,
                'contractor_company':    'شركة البناء الذهبي [DEMO]',
            })

        count = 0
        for tmpl in DEMO_WORK_LOGS:
            boq = boq_map.get(tmpl['boq_code'])
            if not boq:
                continue

            log_date = today - timedelta(days=tmpl['days_ago'])
            log = WorkLog.create({
                'name':          tmpl['name'],
                'mosque_id':     mosque.id,
                'supervisor_id': supervisor.id,
                'boq_id':        boq.id,
                'log_date':      log_date,
                'qty_executed':  tmpl['qty'],
                'state':         tmpl['state'],
                'reject_reason': tmpl.get('reject_reason', False),
                'is_demo':       True,
            })

            if tmpl['state'] == 'rejected':
                log.message_post(
                    body=_('❌ رُفض العمل من الاستشاري.<br/>'
                           '<b>السبب:</b> %s') % tmpl['reject_reason'])
            elif tmpl['state'] == 'approved':
                log.message_post(
                    body=_('✅ اعتمد الاستشاري هذا العمل.'))
            elif tmpl['state'] == 'submitted':
                log.message_post(
                    body=_('📤 تم إرسال العمل للاستشاري — بانتظار الاعتماد.'))

            count += 1

        return count

    def _create_demo_certificate(self, mosque, boq_map):
        Cert     = self.env['mosque.certificate'].sudo()
        CertLine = self.env['mosque.certificate.line'].sudo()
        today    = date.today()

        cert = Cert.create({
            'mosque_id':       mosque.id,
            'cert_number':     1,
            'period_from':     today - timedelta(days=30),
            'period_to':       today - timedelta(days=1),
            'submission_date': today,
            'retention_pct':   10.0,
            'state':           'consultant_review',
            'is_demo':         True,
        })

        # Add 5 BOQ lines to certificate
        cert_items = [
            ('ARCH-01', 45.0),
            ('ARCH-21', 120.0),
            ('ARCH-05', 2.1),
            ('ELEC-52', 1.0),
            ('MECH-43', 1.0),
        ]

        for code, qty in cert_items:
            boq = boq_map.get(code)
            if boq:
                CertLine.create({
                    'certificate_id':  cert.id,
                    'boq_id':          boq.id,
                    'this_period_qty': qty,
                })

        cert.message_post(
            body=_('📤 تم إرسال المستخلص #1 من المقاول.<br/>'
                   'الفترة: %s — %s<br/>'
                   'بانتظار مراجعة الاستشاري.') % (
                cert.period_from, cert.period_to))

        return cert
