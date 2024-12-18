# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import ValidationError
from odoo.addons.invoice_refund.utils.utils import check_if_fields_in_vals, check_if_email_is_valid, \
    check_if_string_is_valid, check_if_number_is_valid, string_to_datestamp


class AccountMove(models.Model):
    _inherit = 'account.move'
    
    reservation_date = fields.Datetime(string="Fecha de reserva")
    payment_due_date_in_case_of_default = fields.Datetime(string="Fecha de cobro en caso de incumplimiento")
    wordpress_reservation_id = fields.Char(string="ID de reserva en Wordpress")
    stripe_refund_ids = fields.One2many('stripe.refund', 'invoice_id', string="Reembolsos Stripe")
    
    payment_state = fields.Selection(
        selection_add=[
            ('stripe_refund', 'Reembolso Stripe'),
            ])
    
    @staticmethod
    def _validate_invoice_json(vals: dict):
        required_fields = [
            "client_name", 
            "client_email", 
            "service_name",
            "service_description",
            "service_price",
            "reservation_date",
            "payment_due_date_in_case_of_default",
            "wordpress_reservation_id",]
        theres_required_fields = check_if_fields_in_vals(
            vals=vals,
            allowed_fields=required_fields,
            flip=True
        )
        if not theres_required_fields:
            raise ValidationError(f"DEBE ENVIAR LOS CAMPOS OBLIGATORIOS: {required_fields}")
        
        if not check_if_string_is_valid(vals.get('client_name')):
            raise ValidationError("El campo 'client_name' es obligatorio.")
        
        if not check_if_string_is_valid(vals.get('client_email')):
            raise ValidationError("El campo 'client_email' es obligatorio.")
        
        if not check_if_email_is_valid(vals.get('client_email')):
            raise ValidationError("El campo 'client_email' debe ser un correo electrónico válido.")
        
        if not check_if_string_is_valid(vals.get('service_name')):
            raise ValidationError("El campo 'service_name' es obligatorio.")
        
        if not check_if_string_is_valid(vals.get('service_description')):
            raise ValidationError("El campo 'service_description' es obligatorio.")
        
        if not check_if_number_is_valid(vals.get('service_price')):
            raise ValidationError("El campo 'service_price' es obligatorio.")
        
        if not check_if_string_is_valid(vals.get('wordpress_reservation_id')):
            raise ValidationError("El campo 'wordpress_reservation_id' es obligatorio.")
        
        try:
            format: str = "%Y-%m-%d %H:%M:%S"
            date_keys = ['reservation_date', 'payment_due_date_in_case_of_default', 'invoice_date']
            for date_key in date_keys:
                if date_key in vals:
                    string_to_datestamp(vals.get(date_key), format=format)
        except Exception as e:
            raise ValidationError(f"El campo '{date_key}' debe ser un string válido y en formato: '{format}'.")
        
    def get_partner_id_from_vals(self, email: str, name: str):
        partner = self.env['res.partner'].search([('email', '=', email)], limit=1)
        if partner:
            return partner.id
        return self.env['res.partner'].create({'email': email, 'name': name}).id
    
    def create_account_move_line_from_vals(self, vals: dict):
        def compose_name(service_name: str, service_description: str):
            return f"{service_name} - {service_description}"
        
        product_id = self.env.ref('invoice_refund.product_service', raise_if_not_found=False)
        account_move_line = self.env['account.move.line'].create({
            'product_id': product_id.id,
            'name': compose_name(vals.get('service_name'), vals.get('service_description')),
            'tax_ids': False,
            'quantity': 1,
            'price_unit': vals.get('service_price'),
            'move_id': self.id,
        })
        return account_move_line
    
    def generate_payment_link(self):
        payment_link = self.env['payment.link.wizard'].create({
            'amount': self.amount_total,
            'currency_id': self.currency_id.id,
            'partner_id': self.partner_id.id,
            'res_model': 'account.move',
            'res_id': self.id,
            'description': self.name,
        })
        return payment_link.link

    @api.model
    def create_invoice(self, vals: dict):
        try:
            self._validate_invoice_json(vals)
            move_vals = {
            'partner_id': self.get_partner_id_from_vals(vals.get('client_email'), vals.get('client_name')),
            'move_type': 'out_invoice',
            'invoice_date': string_to_datestamp(vals.get('invoice_date')) if 'invoice_date' in vals else fields.Date.context_today(self),
            'reservation_date': string_to_datestamp(vals.get('reservation_date')),
            'payment_due_date_in_case_of_default': string_to_datestamp(vals.get('payment_due_date_in_case_of_default')),
            'wordpress_reservation_id': vals.get('wordpress_reservation_id'),
            }
            
            invoice = self.create(move_vals)
            invoice.create_account_move_line_from_vals(vals)
            invoice.action_post()
            payment_link = invoice.generate_payment_link()
           
            return {"success": True, "message": "Factura creada correctamente", "payment_link": payment_link}
        except Exception as e:
            return {"success": False, "message": str(e)}
