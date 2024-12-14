# -*- coding: utf-8 -*-

from odoo import http
from odoo.exceptions import ValidationError
from odoo.addons.invoice_refund.utils.utils import get_vals, get_util_handle_errors_model, get_account_move_model


class InvoiceRefundControllers(http.Controller):

    @http.route('/zona_franca/api/v1/create_invoice', auth='public', methods=['POST'], csrf=False, type='json', cors="*")
    def create_invoice(self):
        try:
            vals = get_vals()
            if not vals:
                raise ValidationError("No se han enviado los datos necesarios para crear la factura.")
            
            account_move = get_account_move_model()
            response = account_move.create_invoice(vals)
            
            return response

        except Exception as e:
            handle_errors = get_util_handle_errors_model()
            response = handle_errors.handle_errors_type_request_http(e)
            return response