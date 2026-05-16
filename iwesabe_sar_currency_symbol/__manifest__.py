# -*- coding: utf-8 -*-
##############################################################################
#
#    iWesabe.
#    Copyright (C) 2018-TODAY iWesabe (<https://www.iwesabe.com>).
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL-3), Version 3.
#
#    It is forbidden to publish, distribute, sublicense, or sell copies
#    of the Software or modified copies of the Software.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL-3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    GENERAL PUBLIC LICENSE (LGPL-3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################
{
    'name': 'New Saudi Riyal Currency Symbol | New SAR Icon',
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'summary': 'New Saudi Riyal Currency Symbol | New SAR Icon',
    'description': """
    - The New Saudi Riyal Symbol can be added to your database after installing this module.
    - Copy This Symbol  and Add it in Saudi Riyal Currency  .
    """,
    'author': 'iWesabe',
    'website': 'https://www.iwesabe.com/',
    'license': 'AGPL-3',
    'depends': ['account'],
    'data': [],
    'assets': {
        'web.assets_backend': [
            'iwesabe_sar_currency_symbol/static/src/css/style.css',
            'iwesabe_sar_currency_symbol/static/src/js/main.js',
        ],
        'web.assets_frontend': [
            'iwesabe_sar_currency_symbol/static/src/css/style.css',
        ],
        'web.report_assets_common': [
            'iwesabe_sar_currency_symbol/static/src/css/style.css',
        ],
        'web.report_assets_pdf': [
            'iwesabe_sar_currency_symbol/static/src/css/style.css',
        ],
    },
    'images': ['static/description/banner.png'],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
