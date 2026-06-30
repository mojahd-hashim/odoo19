# -*- coding: utf-8 -*-
{
    'name': 'اعتماد مخططات ووثائق المشروع',
    'summary': 'دورة اعتماد المخططات والوثائق بين المقاول والاستشاري',
    'description': """
نظام اعتماد الوثائق والمخططات
=============================
- المقاول يرفع طلب اعتماد ويحدد نوع الوثيقة
- رفع ملف-ملف على نفس الطلب (للملفات الكبيرة)
- الاستشاري يعتمد أو يرفض مع ملاحظات
- التخزين على القرص (filestore) وليس قاعدة البيانات
- مرفقات مرتبطة بنظام Documents في Enterprise
    """,
    'version': '19.0.1.0.0',
    'category': 'Project',
    'author': 'makerun.solutions',
    'license': 'LGPL-3',
    'depends': [
        'base', 'mail', 'web',
        'waqf_contractor_portal',
        'contractor_work',
        # 'documents',  # فعّلها إذا كان Enterprise Documents مثبّتاً
    ],
    'data': [
        'security/document_approval_security.xml',
        'security/ir.model.access.csv',
        'data/document_types.xml',
        'data/sequence.xml',
        'views/document_approval_views.xml',
        'views/document_approval_menus.xml',
        'views/portal_templates.xml',
    ],
    'installable': True,
    'application': True,
}
