{
    'name': 'Waqf Mobile API',
    'version': '19.0.1.0.0',
    'category': 'Technical',
    'summary': 'REST API endpoints + mobile settings for Flutter consultant app',
    'description': """
        Provides all backend infrastructure for the Waqf Flutter mobile app:

        ENDPOINTS:
        /api/waqf/auth/login          POST  — authenticate + get token
        /api/waqf/auth/me             GET   — current user profile
        /api/waqf/mosques             GET   — assigned mosques list
        /api/waqf/mosques/<id>        GET   — mosque detail + geofence
        /api/waqf/attendance/checkin  POST  — GPS check-in
        /api/waqf/attendance/checkout POST  — GPS checkout (auto or manual)
        /api/waqf/attendance/active   GET   — active check-in for user
        /api/waqf/attendance/history  GET   — visit history
        /api/waqf/worklogs/pending    GET   — work logs awaiting approval
        /api/waqf/worklogs/<id>/approve POST — approve work log
        /api/waqf/worklogs/<id>/reject  POST — reject with reason
        /api/waqf/supervision/submit  POST  — submit supervision report
        /api/waqf/settings            GET   — app config from Odoo

        FEATURES:
        - Token-based auth (API key per employee)
        - Geofence validation server-side (Haversine)
        - Offline queue support (idempotency keys)
        - Push notification tokens (FCM)
        - App settings configurable from Odoo backend
    """,
    'author': 'Kawaqf IT',
    'website': 'https://www.kawaqf.org',
    'depends': [
        'waqf_mosque_rehab',
        'waqf_mosque_project',
        'waqf_contractor_portal',
        'waqf_consultant_review',
        'hr',
        'web',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/mobile_settings_data.xml',
        'views/mobile_settings_views.xml',
        'views/api_token_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
