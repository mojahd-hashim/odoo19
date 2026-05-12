{
    'name': 'Waqf Consultant Review',
    'version': '19.0.1.0.0',
    'category': 'Project',
    'summary': 'Kanban state management for consultant approval workflow — color-coded task states with CO blocking',
    'description': """
        Extends project.task and project.project with:

        KANBAN STATES (color-coded):
        - Grey   : No update yet (default)
        - Green  : Supervisor submitted update — awaiting consultant review
        - Green✓ : Consultant approved — ready
        - Red    : Rejected — supervisor must correct
        - Yellow🔒: Blocked — Change Order pending approval
        - Orange : Overdue — past deadline

        RULES:
        - Tasks cannot be sent to Waqf unless ALL tasks in project are green (approved)
        - Subtask approval/rejection triggers kanban color update on parent task
        - CO approval automatically unblocks linked tasks
        - Rejection sends automatic notification to supervisor with reason
    """,
    'author': 'Kawaqf IT',
    'website': 'https://www.kawaqf.org',
    'depends': [
        'waqf_mosque_rehab',
        'waqf_mosque_project',
        'waqf_contractor_portal',
        'project',
        'project_enterprise',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/kanban_stages.xml',
        'views/task_kanban_views.xml',
        'views/project_views.xml',
        'views/certificate_views.xml',
        'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
