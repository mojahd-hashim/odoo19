{
    'name': 'Waqf Mosque — Project Integration',
    'version': '19.0.1.0.0',
    'category': 'Project',
    'summary': 'Bridges mosque rehabilitation records with Odoo Project (Gantt, Tasks, Milestones)',
    'description': """
        Extension module that connects waqf_mosque_rehab with project.project:

        - Auto-creates an Odoo Project per mosque on Mobilize
        - Auto-generates 4 milestones per mosque aligned with contract schedule
        - Auto-generates BOQ category tasks assigned to resident engineer
        - Two-way state sync: mosque state ↔ project milestone completion
        - Recurring task templates: weekly quality report, monthly certificate
        - Gantt view across all 29 mosques via project.project list
        - Smart button on mosque form → opens linked project
    """,
    'author': 'Kawaqf IT',
    'website': 'https://www.kawaqf.org',
    'depends': [
        'waqf_mosque_rehab',
        'project',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/project_stage_data.xml',
        'views/mosque_project_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
    'license': 'LGPL-3',
}
