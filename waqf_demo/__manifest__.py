{
    'name': 'Waqf Demo Environment',
    'version': '19.0.1.0.0',
    'category': 'Project',
    'summary': 'Demo mosque with realistic test data for system demonstration and training',
    'description': """
        Creates a fully isolated demo environment:
        - One demo mosque [DEMO-01] with complete BOQ
        - Tasks in all stages with different kanban colors
        - Work logs, change orders, and a pending certificate
        - Demo users (supervisor + consultant)
        - Reset button to wipe and recreate all demo data

        All demo records are tagged is_demo=True so they can be
        excluded from production reports and dashboards.
    """,
    'author': 'Kawaqf IT',
    'website': 'https://www.kawaqf.org',
    'depends': [
        'waqf_mosque_rehab',
        'waqf_mosque_project',
        'waqf_contractor_portal',
        'waqf_consultant_review',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/demo_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
