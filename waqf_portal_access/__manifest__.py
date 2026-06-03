{
    'name':        'Waqf Portal Access Management',
    'version':     '1.0',
    'summary':     'إدارة صلاحيات بوابة المستشارين والمقاولين',
    'description': '''
        موديول شامل للتحكم في صلاحيات المستخدمين على بوابة كوقف:
        - المستشارون المقيمون
        - مهندسو ومشرفو المقاولين
        - إرسال دعوات بالإيميل
        - تفعيل وتعطيل فوري
    ''',
    'author':      'Kawaqf IT',
    'depends':     ['waqf_mosque_rehab', 'waqf_contractor_portal', 'mail', 'portal'],
    'data': [
        'security/ir.model.access.csv',
        'security/groups.xml',
        'data/mail_templates.xml',
        'views/portal_user_views.xml',
        'views/portal_user_form.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
}
