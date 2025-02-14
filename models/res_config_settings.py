from odoo import models, fields, api

class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    invoice_days_to_refund = fields.Integer(string="Días para reembolso de factura", config_parameter='invoice_refund.invoice_days_to_refund')