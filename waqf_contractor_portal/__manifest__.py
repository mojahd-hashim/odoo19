{
    'name': 'Waqf Contractor Portal',
    'version': '19.0.1.0.0',
    'category': 'Website/Portal',
    'summary': 'Contractor supervisor portal for mosque rehabilitation — BOQ tracking, subtasks, evidence photos',
    'description': """
        Portal for contractor supervisors (one per mosque site):
        - Request BOQ access per mosque (audited)
        - View scheduled tasks by planned date
        - Log daily work as subtasks linked to BOQ items
        - Upload evidence photos per subtask
        - Trigger change order requests when quantities exceed contract
        - Full Arabic RTL interface
    """,
    'author': 'Kawaqf IT',
    'website': 'https://www.kawaqf.org',
    'depends': [
        'waqf_mosque_rehab',
        'waqf_mosque_project',
        'portal',
        'website',
        'project',
    ],
    'data': [
        'security/portal_security.xml',
        'security/ir.model.access.csv',
        'data/portal_data.xml',
        'views/portal_templates.xml',
        'views/portal_work_log.xml',
        'views/portal_log_history.xml',
        'views/portal_certificate.xml',
        'views/portal_change_order.xml',
        'views/portal_assets.xml',
        'views/contractor_boq_access.xml',
        'views/contractor_work_log.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
