import requests
import json
from datetime import datetime

from odoo import models, fields, api
from  odoo.exceptions import ValidationError

OPTIONS = [
    ('absence', 'Falta de asistencia'),
    ('duplicate', 'Duplicado'),
    ('fraudulent', 'Fraudulento'),
    ('requested_by_customer', 'Solicitado por el cliente'),
    ('other', 'Otro'),
    ]

def get_option(options: list, key: str) -> str:
    """
    Retrieve the value associated with a given key from a list of options.
    Args:
        options (list): A list of tuples where each tuple contains a key-value pair.
        key (str): The key for which the corresponding value needs to be retrieved.
    Returns:
        str: The value associated with the given key if found, otherwise an empty string.
    """
    
    if not key:
        return ""
    
    reason = list(filter(lambda opt: opt[0] == key, options))
    return reason[0][1] if reason else ""

class StripeRequestHandler:
    """
    A handler for making requests to the Stripe API, specifically for creating refunds.
    Attributes:
        endpoints (dict): A dictionary containing the API endpoints.
        api_key (str): The API key used for authenticating requests.
        __data (dict): A private attribute to store the data for the request.
    Properties:
        headers (dict): Returns the headers required for the request.
        data (dict): Gets or sets the data for the request.
    Methods:
        refund(): Sends a refund request to the Stripe API.
    """
    
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
        """
        Sends a POST request to the 'create_refund' endpoint to create a refund.
        This method retrieves the URL for the 'create_refund' endpoint from the 
        `endpoints` attribute, and sends a POST request with the headers and data 
        specified in the `headers` and `data` attributes, respectively.
        Returns:
            dict: A dictionary containing the status code of the response and the 
                  JSON response content.
                  Example:
                  {
                      "status_code": 200,
                      "response": {...}
        """
        
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
        if invoice.stripe_refund_count == 0 and invoice.stripe_refunded_amount == 0:
            return invoice.amount_total
        
        return invoice.amount_total - invoice.stripe_refunded_amount

    invoice_id = fields.Many2one('account.move', string="Factura", default= lambda self: self._default_invoice(), retured=True)
    currency_id = fields.Many2one('res.currency', string="Moneda", related='invoice_id.currency_id', readonly=True)
    refund_reason = fields.Selection(
        OPTIONS,
        string="Motivo del reembolso",
        default='absence',
    )
    refund_description = fields.Text(string="Descripción del reembolso")
    amount = fields.Monetary(
        string="Monto", 
        currency_field='currency_id', 
        default=lambda self: self._default_amount(), 
        required=True
        )

    @api.onchange('refund_reason')
    def _onchange_refund_reason(self):
        if self.refund_reason == 'absence':
            self.amount = self._default_amount() / 2
        else:
            self.amount = self._default_amount()
    
    @api.constrains('amount')
    def _check_amount(self):
        for record in self:
            if record.invoice_id.stripe_refund_count == 0:
                if record.amount > record.invoice_id.amount_total:
                    raise ValidationError("El monto a reembolsar no puede ser mayor que el monto de la factura")
                return None
                
            if record.invoice_id.stripe_fully_refunded:
                raise ValidationError("La factura ya ha sido completamente reembolsada")
            
            if not record.invoice_id.stripe_fully_refunded:
                diff = record.invoice_id.amount_total - record.invoice_id.stripe_refunded_amount
                if record.amount > diff:
                    currency = record.invoice_id.currency_id.symbol
                    raise ValidationError(f"El monto a reembolsar no puede ser mayor que el monto restante de la factura: {currency} {diff:,.2f}".replace('.', ','))
            
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
        """
        Retrieve the charge ID for a given provider.
        This method filters the transaction IDs associated with the invoice to find the one
        that matches the specified provider ID and has a state of 'done'. It then returns
        the provider reference of the matching transaction.
        Args:
            provider_id (int): The ID of the provider to filter transactions by.
        Returns:
            str: The provider reference of the matching transaction.
        """
        
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
        """
        Process the refund of an invoice using Stripe.
        This method handles the refund process by interacting with the Stripe API.
        It prepares the necessary data, sends the refund request, and processes
        the response. If the refund is successful, it creates a record of the refund
        and updates the invoice payment state.
        Raises:
            ValidationError: If the refund request fails or the response status code is not 200.
        Returns:
            None
        """
        
        stripe_provider = self._get_stripe_payment_provider()
        stripe = StripeRequestHandler(
            api_key=stripe_provider.stripe_secret_key
            )
        
        stripe.data = self._prepare_data(provider_id=stripe_provider.id)
        response = stripe.refund()
        
        if response.get('status_code') != 200:
            raise ValidationError(f"Error al procesar la solicitud de reembolso: {response.get('response')}")
        
        response = response.get('response')
        if response.get('status') == 'succeeded':
            
            #create stripe refund record
            self.env['stripe.refund'].create({
                "refund_id": response.get('id'),
                "invoice_id": self.invoice_id.id,
                "amount_refunded": self.amount,
                "charge": response.get('charge'),
                "created": datetime.fromtimestamp(response.get('created')),
                "refund_status": response.get('status'),
                "reason":  get_option(OPTIONS, response.get('reason')),
                "description": self.refund_description if self.refund_description else ""
            })
            
            #update invoice payment state
            self.invoice_id.write({
                "payment_state": "stripe_refund"
            })
        
        