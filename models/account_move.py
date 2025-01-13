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
    stripe_refund_count = fields.Integer(string="Cantidad de reembolsos Stripe", compute='_compute_stripe_refund_count')
    stripe_refunded_amount = fields.Monetary(string="Monto reembolsado", compute='_compute_stripe_refunded_amount', store=True)
    stripe_fully_refunded = fields.Boolean(string="Totalmente reembolsado", compute='_compute_stripe_fully_refunded', store=True)
    
    @api.depends('stripe_refund_ids')
    def _compute_stripe_refunded_amount(self):
        for record in self:
            if record.stripe_refund_ids:
                record.stripe_refunded_amount = sum(record.stripe_refund_ids.mapped('amount_refunded'))
            else:
                record.stripe_refunded_amount = 0
    
    @api.depends('amount_total', 'stripe_refunded_amount')
    def _compute_stripe_fully_refunded(self):
        for record in self:
            if record.amount_total:
                record.stripe_fully_refunded = record.amount_total == record.stripe_refunded_amount
            else:
                record.stripe_fully_refunded = False
    
    @api.depends('stripe_refund_ids')
    def _compute_stripe_refund_count(self):
        for record in self:
            record.stripe_refund_count = len(record.stripe_refund_ids)
    
    payment_state = fields.Selection(
        selection_add=[
            ('stripe_refund', 'Reembolso Stripe'),
            ])
    
    @staticmethod
    def _validate_invoice_json(vals: dict):
        """
        Validates the provided invoice JSON data.
        Args:
            vals (dict): A dictionary containing the invoice data to be validated.
        Raises:
            ValidationError: If any of the required fields are missing or invalid.
        Required Fields:
            - client_name (str): The name of the client.
            - client_email (str): The email of the client.
            - service_name (str): The name of the service.
            - service_description (str): The description of the service.
            - service_price (float): The price of the service.
            - reservation_date (str): The reservation date in the format '%Y-%m-%d %H:%M:%S'.
            - payment_due_date_in_case_of_default (str): The payment due date in case of default in the format '%Y-%m-%d %H:%M:%S'.
            - wordpress_reservation_id (str): The WordPress reservation ID.
        Validation Steps:
            1. Checks if all required fields are present in the `vals` dictionary.
            2. Validates that `client_name`, `client_email`, `service_name`, `service_description`, and `wordpress_reservation_id` are valid strings.
            3. Validates that `client_email` is a valid email address.
            4. Validates that `service_price` is a valid number.
            5. Validates that `reservation_date`, `payment_due_date_in_case_of_default`, and `invoice_date` (if present) are valid date strings in the format '%Y-%m-%d %H:%M:%S'.
        """
        
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
        """
        Create an account move line from the provided values.
        This method creates an account move line using the provided values dictionary.
        It composes the name of the move line using the service name and description,
        retrieves the product service reference, and sets the necessary fields for the
        account move line.
        Args:
            vals (dict): A dictionary containing the following keys:
                - service_name (str): The name of the service.
                - service_description (str): The description of the service.
                - service_price (float): The price of the service.
        Returns:
            recordset: The created account move line record.
        """
        
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
        """
        Generates a payment link for the current account move.
        This method creates a new payment link using the 'payment.link.wizard' model
        with the relevant details from the current account move, such as the total amount,
        currency, partner, model, record ID, and description.
        Returns:
            str: The generated payment link.
        """
        
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
        """
        Creates an invoice based on the provided values.
        Args:
            vals (dict): A dictionary containing the invoice details. Expected keys include:
                - 'client_email' (str): The email of the client.
                - 'client_name' (str): The name of the client.
                - 'invoice_date' (str, optional): The date of the invoice.
                - 'reservation_date' (str): The reservation date.
                - 'payment_due_date_in_case_of_default' (str): The payment due date in case of default.
                - 'wordpress_reservation_id' (str): The WordPress reservation ID.
        Returns:
            dict: A dictionary with the result of the invoice creation. Contains:
                - 'success' (bool): True if the invoice was created successfully, False otherwise.
                - 'message' (str): A message indicating the result of the operation.
                - 'payment_link' (str, optional): The payment link if the invoice was created successfully.
        """
        
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
        
    def action_view_stripe_refunds(self):
        refunds = self.stripe_refund_ids
        action = self.env['ir.actions.actions']._for_xml_id('invoice_refund.action_stripe_refund')
        if len(refunds) > 1:
            action['domain'] = [('id', 'in', refunds.ids)]
        elif len(refunds) == 1:
            form_view = [(self.env.ref('invoice_refund.view_stripe_refund_form').id, 'form')]
            if 'views' in action:
                action['views'] = form_view + [(state, view) for state, view in action['views'] if view != 'form']
            else:
                action['views'] = form_view
            action['res_id'] = refunds.id
        else:
            action = {'type': 'ir.actions.act_window_close'}
            
        context = self.env.context.copy()
        if len(self) == 1:
            context.update({
                'default_invoice_id': self.id,
                'default_partner_id': self.partner_id.id,
            })
        action['context'] = context
        return action
