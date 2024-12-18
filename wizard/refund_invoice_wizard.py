import requests
import json

from odoo import models, fields, api
from  odoo.exceptions import ValidationError

class StripeRequestHandler:
    endpoints = {
        'create_refund': 'https://api.stripe.com/v1/refunds'
    }
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.__data = {}
        
    @property
    def headers(self):
        return {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {self.api_key}"
        }
        
    @property
    def data(self):
        return self.__data
    
    @data.setter
    def data(self, data: dict):
        if not isinstance(data, dict):
            raise ValueError("data debe ser un diccionario")
        
        self.__data = data
        
    def refund(self):
        url = self.endpoints.get('create_refund')
        response = requests.post(url, headers=self.headers, data=self.data)
        return {
            "status_code": response.status_code, 
            "response": response.json()
        }

class RefundInvoiceWizard(models.TransientModel):
    _name = 'refund.invoice.wizard'
    _description = 'Refund Invoice Wizard'

    def _default_invoice(self):
        return self.env['account.move'].browse(self._context.get('active_id'))
    
    def _default_amount(self):
        invoice = self.env['account.move'].browse(self._context.get('active_id'))
        return invoice.amount_total

    invoice_id = fields.Many2one('account.move', string="Factura", default= lambda self: self._default_invoice(), retured=True)
    currency_id = fields.Many2one('res.currency', string="Moneda", related='invoice_id.currency_id', readonly=True)
    refund_reason = fields.Selection(
        [
            ('duplicate', 'Duplicado'),
            ('fraudulent', 'Fraudulento'),
            ('requested_by_customer', 'Solicitado por el cliente'),
            ('other', 'Otro'),
        ],
        string="Motivo del reembolso",
    )
    refund_description = fields.Text(string="Descripción del reembolso")
    amount = fields.Monetary(
        string="Monto", 
        currency_field='currency_id', 
        default=lambda self: self._default_amount(), 
        required=True
        )
    
    @api.constrains('amount')
    def _check_amount(self):
        for record in self:
            if record.amount > record.invoice_id.amount_total:
                raise ValidationError("El monto a reembolsar no puede ser mayor que el monto de la factura")
            
    def _get_stripe_payment_provider(self):
        stripe_payment_provider = self.env.ref('payment.payment_provider_stripe', raise_if_not_found=False)
        if not stripe_payment_provider:
            raise ValidationError("Proveedor de pago 'Stripe' no encontrado!")
        
        if stripe_payment_provider.state not in  ['enabled', 'test']:
            raise ValidationError("Proveedor de pago 'Stripe' no está habilitado!")
        
        if not stripe_payment_provider.stripe_publishable_key:
            raise ValidationError("La llave pública de Stripe no ha sido configurada!")
        
        if not stripe_payment_provider.stripe_secret_key:
            raise ValidationError("La llave secreta de Stripe no ha sido configurada!")
        
        if not stripe_payment_provider.is_published:
            raise ValidationError("El proveedor de pago 'Stripe' no está publicado!")
        
        return stripe_payment_provider
    
    def _get_charge_id(self, provider_id: int) -> str:
        return self.invoice_id.transaction_ids.filtered(lambda tx: tx.state == 'done'\
            and tx.provider_id.id == provider_id).provider_reference
        
    def _prepare_data(self, provider_id: int) -> dict:
        charge_id = self._get_charge_id(provider_id=provider_id)
        
        if not charge_id:
            raise ValidationError("No se encontró el ID de la transacción de pago")
        
        data = {
            "charge": charge_id,
            "metadata[invoice_id]": self.invoice_id.id,
            "metadata[invoice_number]": self.invoice_id.name,
            "metadata[partner_id]": self.invoice_id.partner_id.id,
            "metadata[partner_name]": self.invoice_id.partner_id.name,
            "metadata[partner_email]": self.invoice_id.partner_id.email,
        }
        
        if self.refund_reason and self.refund_reason != 'other':
            data['reason'] = self.refund_reason
        
        if self.amount < self.invoice_id.amount_total:
            data['amount'] = int(self.amount * 100)
        
        if self.refund_description:
            data['metadata[refund_description]'] = self.refund_description
        
        return data

    def refund_invoice(self):
        stripe_provider = self._get_stripe_payment_provider()
        stripe = StripeRequestHandler(
            api_key=stripe_provider.stripe_secret_key
            )
        
        stripe.data = self._prepare_data(provider_id=stripe_provider.id)
        response = stripe.refund()
        
        if response.get('status_code') != 200:
            raise ValidationError(f"Error al procesar la solicitud de reembolso: {response.get('response')}")
        