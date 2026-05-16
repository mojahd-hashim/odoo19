# -*- coding: utf-8 -*-
{
    'name': 'Waqf Mosque AI Risk Center',
    'version': '19.0.1.0.0',
    'category': 'Project/Project Management',
    'summary': 'AI-ready risk data layer for mosque rehabilitation projects',
    'description': '''
AI Risk Center data and analysis layer for Mosque Rehabilitation.
Collects periodic snapshots, applies rule-based alerts, optionally calls Azure OpenAI,
and exposes dashboard APIs.
    ''',
    'author': 'Kawaqf IT',
    'website': 'https://kawaqf.org',
    'depends': [
        'base',
        'mail',
        'project',
        'web',
        'waqf_mosque_rehab',
    ],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron.xml',
        'views/ai_run_views.xml',
        'views/ai_snapshot_views.xml',
        'views/ai_alert_views.xml',
        'views/ai_prediction_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
