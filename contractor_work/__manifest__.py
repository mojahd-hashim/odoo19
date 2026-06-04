{
    'name':        'Contractor Work Orders',
    'version':     '1.0',
    'summary':     'إدارة أوامر عمل المقاولين — بدء، تسليم، اختبار، ضمان',
    'author':      'Kawaqf IT',
    'depends':     ['mosque_management', 'project', 'hr', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'data/config_data.xml',
        'views/work_order_views.xml',
        'views/qualification_views.xml',
        'views/material_submittal_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
}
