{
    'name': 'Waqf Executive Dashboard',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'Interactive executive dashboard for Waqf mosque rehabilitation project management',
    'description': """
        Full-featured executive dashboard at /dashboard:
        - Real-time KPI cards (financial, time, supervision)
        - Interactive Gantt chart with deviation alerts
        - 29-mosque performance heatmap
        - Task details with subtasks, photo gallery, document viewer
        - Certificate & Change Order approval panel
        - Field visit reports & attendance timeline
        - Live consultant presence map
        - Floating AI chatbot (Azure OpenAI)
        - Live stream notification & viewer
        - Company branding from system settings
    """,
    'author': 'Kawaqf IT',
    'website': 'https://www.kawaqf.org',
    'depends': [
        'waqf_mosque_rehab',
        'waqf_mosque_project',
        'waqf_contractor_portal',
        'waqf_consultant_review',
        'website',
        'web',
        'base_setup',
    ],
    'data': [
        'security/ir.model.access.csv',
        'views/dashboard_template.xml',
        'views/live.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}