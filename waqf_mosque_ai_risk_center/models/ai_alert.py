# -*- coding: utf-8 -*-
from datetime import timedelta
from odoo import api, fields, models, _


class WaqfAiAlert(models.Model):
    _name = 'waqf.ai.alert'
    _description = 'Smart AI Risk Alert'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'severity desc, priority_score desc, create_date desc'

    name = fields.Char(required=True, tracking=True)
    run_id = fields.Many2one('waqf.ai.snapshot.run', ondelete='cascade', index=True)
    phase_id = fields.Many2one('mosque.package', index=True)
    mosque_id = fields.Many2one('mosque.mosque', index=True)
    contractor = fields.Char(index=True)
    alert_type = fields.Selection([
        ('delay', 'Delay'), ('financial', 'Financial'), ('approval', 'Approval'),
        ('quality', 'Quality'), ('supervision', 'Supervision'), ('boq', 'BOQ'),
        ('contractor', 'Contractor'), ('change_order', 'Change Order'),
        ('payment_execution_impact', 'Payment Execution Impact'),
        ('data_conflict', 'Data Conflict'), ('silent_project', 'Silent Project'), ('risk', 'Risk'),
    ], required=True, index=True)
    severity = fields.Selection([('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')], default='medium', required=True, tracking=True, index=True)
    status = fields.Selection([('new', 'New'), ('acknowledged', 'Acknowledged'), ('in_progress', 'In Progress'), ('resolved', 'Resolved'), ('dismissed', 'Dismissed')], default='new', tracking=True, index=True)
    title = fields.Char(required=True, tracking=True)
    summary = fields.Text()
    root_cause = fields.Text()
    impact = fields.Text()
    phase_impact = fields.Text()
    recommendation = fields.Text()
    confidence = fields.Float()
    source = fields.Selection([('rule', 'Rule'), ('ai', 'AI'), ('hybrid', 'Hybrid')], default='rule', required=True)
    priority_score = fields.Integer(index=True)
    impact_score = fields.Integer()
    probability_score = fields.Integer()
    related_metrics_json = fields.Json()
    ai_payload_json = fields.Json()
    assigned_user_id = fields.Many2one('res.users', tracking=True)
    due_date = fields.Date()
    acknowledged_by = fields.Many2one('res.users')
    acknowledged_date = fields.Datetime()
    resolved_by = fields.Many2one('res.users')
    resolved_date = fields.Datetime()
    active = fields.Boolean(default=True)

    def action_acknowledge(self):
        self.write({'status': 'acknowledged', 'acknowledged_by': self.env.user.id, 'acknowledged_date': fields.Datetime.now()})

    def action_in_progress(self):
        self.write({'status': 'in_progress'})

    def action_resolve(self):
        self.write({'status': 'resolved', 'resolved_by': self.env.user.id, 'resolved_date': fields.Datetime.now()})

    def action_dismiss(self):
        self.write({'status': 'dismissed', 'active': False})

    def action_open_mosque(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'mosque.mosque', 'res_id': self.mosque_id.id, 'view_mode': 'form', 'target': 'current'}

    def action_open_related_certificates(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Related Certificates'), 'res_model': 'mosque.certificate', 'view_mode': 'list,form', 'domain': [('mosque_id', '=', self.mosque_id.id)]}

    def action_open_related_reports(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Related Reports'), 'res_model': 'mosque.supervision', 'view_mode': 'list,form', 'domain': [('mosque_id', '=', self.mosque_id.id)]}

    @api.model
    def _generate_rule_alerts(self, run, snapshots):
        created = []
        delayed_by_contractor = {}
        for s in snapshots:
            contractor = s.get('contractor') or ''
            if s.get('days_delay', 0) > 0:
                delayed_by_contractor.setdefault(contractor, 0)
                delayed_by_contractor[contractor] += 1

            if s.get('pending_certificates_value', 0) > 0 and s.get('oldest_pending_certificate_days', 0) >= 7 and (s.get('days_delay', 0) > 0 or s.get('numeric_snapshot_json', {}).get('financial_time_variance', 0) < 5):
                created.append(self._create_or_update_alert(run, self._rule_payload(s, 'payment_execution_impact', 'high', 'دفعات معلقة قد تؤثر على التنفيذ', 'وجود مستخلصات معلقة لمدة تتجاوز 7 أيام مع مؤشرات تأخر أو ضعف تقدم.'), 'rule'))
            if s.get('financial_progress', 0) - s.get('time_progress', 0) >= 20:
                created.append(self._create_or_update_alert(run, self._rule_payload(s, 'financial', 'high', 'انحراف مالي مقابل زمني', 'التقدم المالي أعلى من التقدم الزمني بفارق مؤثر.'), 'rule'))
            if s.get('validated_visits_7d', 0) < 2 or s.get('days_since_last_report', 999) > 7:
                created.append(self._create_or_update_alert(run, self._rule_payload(s, 'supervision', 'medium', 'ضعف إشراف ميداني', 'عدد الزيارات الموثقة أو حداثة التقارير أقل من الحد المطلوب.'), 'rule'))
            if s.get('days_since_last_report', 999) > 7 and s.get('attendance_count_7d', 0) == 0 and s.get('state') in ('active', 'in_progress', 'progress'):
                created.append(self._create_or_update_alert(run, self._rule_payload(s, 'silent_project', 'critical', 'مشروع صامت', 'لا توجد تقارير أو زيارات حديثة رغم أن المشروع نشط.'), 'rule'))
            if s.get('ncr_count_30d', 0) > 0 or s.get('safety_incidents_30d', 0) > 0:
                created.append(self._create_or_update_alert(run, self._rule_payload(s, 'quality', 'high', 'خطر جودة أو سلامة', 'وجود NCR أو حوادث سلامة خلال آخر 30 يوم.'), 'rule'))
            if s.get('pending_change_orders_count', 0) > 0 or s.get('blocked_tasks_count', 0) > 0:
                created.append(self._create_or_update_alert(run, self._rule_payload(s, 'change_order', 'high', 'تعطيل بسبب أمر تغيير', 'وجود أوامر تغيير معلقة أو مهام مجمدة بسبب أمر تغيير.'), 'rule'))
            if s.get('time_progress', 0) - s.get('boq_execution_percent', 0) >= 20:
                created.append(self._create_or_update_alert(run, self._rule_payload(s, 'boq', 'high', 'تأخر تنفيذ البنود', 'نسبة تنفيذ BOQ أقل من التقدم الزمني بفارق كبير.'), 'rule'))
            latest_issues = (s.get('text_snapshot_json') or {}).get('latest_issues') or ''
            if not latest_issues.strip() and (s.get('days_delay', 0) > 0 or s.get('boq_execution_percent', 0) + 20 < s.get('time_progress', 0)):
                created.append(self._create_or_update_alert(run, self._rule_payload(s, 'data_conflict', 'medium', 'تعارض بين التقرير والمؤشرات', 'التقارير لا تعرض مشاكل واضحة بينما المؤشرات الرقمية تشير إلى تأخر أو ضعف إنجاز.'), 'rule'))

        for contractor, count in delayed_by_contractor.items():
            if contractor and count > 2:
                payload = {
                    'title': 'نمط تأخر متكرر لدى المقاول', 'alert_type': 'contractor', 'severity': 'high',
                    'mosque_id': False, 'contractor': contractor,
                    'summary': 'لدى المقاول أكثر من مسجدين متأخرين في المرحلة الحالية.',
                    'root_cause': 'نمط أداء متكرر على مستوى المقاول.',
                    'impact': 'احتمال امتداد التأخير على عدة مواقع.',
                    'phase_impact': 'قد يؤثر على إنجاز المرحلة إجمالًا.',
                    'recommendation': 'عقد اجتماع أداء مع المقاول ومراجعة الموارد والسيولة وخطة التعافي.',
                    'confidence': 0.85, 'priority_score': 80, 'impact_score': 80, 'probability_score': 80,
                    'related_metrics': {'delayed_mosques_count': count},
                }
                created.append(self._create_or_update_alert(run, payload, 'rule'))
        critical_count = len([a for a in created if a and a.severity == 'critical'])
        if critical_count >= 3:
            self._create_or_update_alert(run, {
                'title': 'خطر تعثر المرحلة', 'alert_type': 'risk', 'severity': 'critical',
                'summary': 'عدد المشاريع الحرجة في المرحلة تجاوز الحد الآمن.',
                'root_cause': 'تراكم مخاطر زمنية/إشرافية/اعتمادية.',
                'impact': 'احتمال تأثر تاريخ إغلاق المرحلة.',
                'phase_impact': 'مرتفع على مستوى المرحلة.',
                'recommendation': 'تفعيل غرفة متابعة تنفيذية للمشاريع الحرجة.',
                'confidence': 0.8, 'priority_score': 90, 'impact_score': 90, 'probability_score': 80,
                'related_metrics': {'critical_count': critical_count},
            }, 'rule')
        return [a.related_metrics_json for a in created if a]

    @api.model
    def _rule_payload(self, s, alert_type, severity, title, summary):
        score = {'low': 30, 'medium': 55, 'high': 75, 'critical': 95}.get(severity, 50)
        return {
            'title': title, 'alert_type': alert_type, 'severity': severity,
            'mosque_id': s.get('mosque_id'), 'contractor': s.get('contractor'),
            'summary': summary,
            'root_cause': summary,
            'impact': 'قد يؤثر على سرعة التنفيذ أو جودة القرار أو انتظام المرحلة.',
            'phase_impact': 'يتطلب متابعة ضمن مؤشرات المرحلة الحالية.',
            'recommendation': 'مراجعة التفاصيل واتخاذ إجراء تصحيحي مع الجهة المسؤولة.',
            'confidence': 0.75, 'priority_score': score, 'impact_score': score, 'probability_score': score,
            'related_metrics': s,
        }

    @api.model
    def _create_or_update_alert(self, run, item, source='rule'):
        mosque_id = item.get('mosque_id') or False
        title = item.get('title') or _('Risk Alert')
        alert_type = item.get('alert_type') or 'risk'
        since = fields.Datetime.now() - timedelta(hours=24)
        domain = [('alert_type', '=', alert_type), ('title', '=', title), ('create_date', '>=', since)]
        if mosque_id:
            domain.append(('mosque_id', '=', mosque_id))
        if item.get('contractor'):
            domain.append(('contractor', '=', item.get('contractor')))
        existing = self.search(domain, limit=1)
        vals = {
            'name': title,
            'run_id': run.id,
            'phase_id': run.phase_id.id,
            'mosque_id': mosque_id,
            'contractor': item.get('contractor'),
            'alert_type': alert_type,
            'severity': item.get('severity') or 'medium',
            'title': title,
            'summary': item.get('summary'),
            'root_cause': item.get('root_cause'),
            'impact': item.get('impact'),
            'phase_impact': item.get('phase_impact'),
            'recommendation': item.get('recommendation'),
            'confidence': float(item.get('confidence') or 0.0),
            'source': 'hybrid' if existing and existing.source != source else source,
            'priority_score': int(item.get('priority_score') or 0),
            'impact_score': int(item.get('impact_score') or 0),
            'probability_score': int(item.get('probability_score') or 0),
            'related_metrics_json': item.get('related_metrics') or item.get('related_metrics_json') or {},
            'ai_payload_json': item if source == 'ai' else {},
        }
        if existing:
            existing.write(vals)
            return existing
        return self.create(vals)
