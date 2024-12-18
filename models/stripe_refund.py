from odoo import models, fields, api

class StripeRefund(models.Model):
    _name = 'stripe.refund'
    _description = 'Stripe Refund'
    
    refund_id = fields.Char(string="ID de reembolso", required=True)
    invoice_id = fields.Many2one('account.move', string="Factura", required=True)
    currency_id = fields.Many2one('res.currency', string="Moneda", related='invoice_id.currency_id', readonly=True)
    amount_refunded = fields.Monetary(string="Monto reembolsado", currency_field='currency_id', required=True)
    charge = fields.Char(string="Cargo", required=True)
    created = fields.Datetime(string="Creado", required=True)
    sequence = fields.Integer(default=10)
    refund_status = fields.Char(string="Estado de reembolso", required=True)
    partner_id = fields.Many2one('res.partner', string="Cliente", related='invoice_id.partner_id', readonly=True)
    
   