{
    'name': 'Waqf Portal Theme',
    'version': '19.0.1.0.0',
    'category': 'Website',
    'summary': 'Custom landing page + branded login for Waqf mosque rehabilitation system',
    'description': """
        Replaces Odoo default login & home pages with:
        - Branded landing page at / with 3 entry gates
        - Custom split-screen login at /web/login
        - Contractor portal redirect
        - Dashboard shortcut for managers
        All reflecting Kawaqf visual identity: Navy / Teal / Gold
    """,
    'author': 'Kawaqf IT',
    'website': 'https://www.kawaqf.org',
    'depends': [
        'web',
        'website',
        'auth_signup',
        'waqf_mosque_rehab',
        'waqf_contractor_portal',
    ],
    'data': [
        'views/landing_page.xml',
        'views/login_page.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
