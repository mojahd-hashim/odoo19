{
    'name':        'Contractor Work Orders',
    'version':     '1.0',
    'summary':     'إدارة أوامر عمل المقاولين — بدء، تسليم، اختبار، ضمان',
    'author':      'Kawaqf IT',
    'depends':     ['waqf_mosque_rehab', 'project', 'hr', 'mail'],
    'data': [
        'security/ir.model.access.csv',
        'security/work_order_record_rules.xml',
        'data/config_data.xml',
        'views/work_order_views.xml',
        'views/qualification_views.xml',
        'views/material_submittal_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
}
