{
    'name': 'Waqf Mosque Rehabilitation',
    'version': '19.0.1.0.0',
    'category': 'Project',
    'summary': 'Comprehensive management for mosque rehabilitation projects — Waqf King Abdullah',
    'description': """
        Full lifecycle management for 29 mosque rehabilitation projects:
        - Mosque registry with geographic packages
        - Bill of Quantities (BOQ) per mosque
        - Supervision visit tracking with GPS/QR validation
        - Monthly payment certificates (Istikhlassat)
        - Multi-level approval workflow (Contractor → Consultant → Waqf)
        - Change order management
        - Executive dashboard with KPIs
    """,
    'author': 'Kawaqf IT',
    'website': 'https://www.kawaqf.org',
    'depends': [
        'base',
        'mail',
        'hr',
        'account',
        'project',
        'documents',
        'web',
    ],
    'data': [
        'security/mosque_security.xml',
        'security/ir.model.access.csv',
        'data/mosque_sequence.xml',
        'data/mosque_package_data.xml',
        'data/boq_template_data.xml',
        'data/workforce_types.xml',
        'views/mosque_views.xml',
        'views/boq_views.xml',
        'views/supervision_views.xml',
        'views/certificate_views.xml',
        'views/change_order_views.xml',
        'views/attendance_views.xml',
        'views/dashboard_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
    'images': ['static/description/banner.png'],
}
