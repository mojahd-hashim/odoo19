{
    'name': 'المستخلصات المالية — تأهيل المساجد',
    'summary': 'دورة اعتماد المستخلصات: استشاري → مهندس الوقف → المدير → API',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'author': 'makerun.solutions',
    'license': 'LGPL-3',
    'depends': [
        'base', 'mail', 'web',
        'contractor_work',
        'waqf_contractor_portal',
    ],
    'data': [
        'security/payment_claim_security.xml',
        'security/ir.model.access.csv',
        'data/sequence.xml',
        'views/payment_claim_views.xml',
        'views/payment_claim_menus.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': True,
}
