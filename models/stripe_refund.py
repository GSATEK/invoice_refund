from odoo import models, fields, api

class StripeRefund(models.Model):
    """
    A model representing a Stripe refund.
    Attributes:
        refund_id (fields.Char): The unique identifier for the refund. Required.
        invoice_id (fields.Many2one): A reference to the associated invoice (account.move). Required.
        currency_id (fields.Many2one): The currency of the refund, related to the invoice's currency. Read-only.
        amount_refunded (fields.Monetary): The amount that has been refunded. Required.
        charge (fields.Char): The charge associated with the refund. Required.
        created (fields.Datetime): The datetime when the refund was created. Required.
        sequence (fields.Integer): The sequence order for the refund. Default is 10.
        refund_status (fields.Char): The status of the refund. Required.
        partner_id (fields.Many2one): A reference to the customer (res.partner) associated with the invoice. Read-only.
        reason (fields.Char): The reason for the refund.
        description (fields.Text): A description of the refund.
    """
    
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
    reason = fields.Char(string="Motivo")
    description = fields.Text(string="Descripción")
   