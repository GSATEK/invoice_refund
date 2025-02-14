# -*- coding: utf-8 -*-
{
    'name': "invoice_refund",

    'summary': """
        Creates a refund invoices and refunds for reservations""",

    'description': """
       Creates a refund invoices and refunds for reservations through API and return links
       to pay using Stripe.
    """,
    'author': "Kit digital",
    
    'category': 'Accounting/Accounting',
    'version': '0.1',

    'depends': ['account', 'website', 'contacts'],

    'data': [
        'security/ir.model.access.csv',
        'data/products.xml',
        'wizard/refund_invoice_wizard.xml',
        'views/account_move.xml',
        'views/stripe_refund.xml',
        'views/res_config_settings_view.xml',
        'data/crons.xml',
    ],
}
