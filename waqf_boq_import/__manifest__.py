{
    'name': 'Waqf BOQ Import Wizard',
    'version': '19.0.1.0.0',
    'category': 'Project',
    'summary': 'Import 1,769 BOQ lines from Excel into mosque rehabilitation module',
    'description': """
        Provides a wizard to import Bill of Quantities from the contract Excel file.
        Three modes:
        1. Load All — uses embedded data (1,769 lines, all 29 mosques, no file needed)
        2. JSON File — upload a pre-processed JSON export
        3. Excel File — upload the raw BOQ Excel directly
    """,
    'author': 'Kawaqf IT',
    'depends': ['waqf_mosque_rehab'],
    'data': [
        'security/ir.model.access.csv',
        'wizard/boq_import_views.xml',
        # 'views/menu_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
