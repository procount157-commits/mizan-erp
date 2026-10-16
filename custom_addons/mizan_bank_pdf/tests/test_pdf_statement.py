# -*- coding: utf-8 -*-
import os

from odoo.tests import TransactionCase, tagged

from ..models.pdf_statement import StatementError, parse_statement

HERE = os.path.dirname(__file__)


@tagged("post_install", "-at_install")
class TestPdfStatement(TransactionCase):

    def _sample(self):
        with open(os.path.join(HERE, "sample_statement.pdf"), "rb") as f:
            return f.read()

    def test_reads_every_row_and_balances(self):
        parsed = parse_statement(self._sample())
        self.assertEqual(parsed["account_number"], "AE070331234567890123456")
        self.assertEqual(parsed["currency"], "AED")
        self.assertEqual(parsed["balance_start"], 2699050.00)
        self.assertEqual(parsed["balance_end"], 3580854.73)
        self.assertEqual(len(parsed["transactions"]), 11)
        first = parsed["transactions"][0]
        self.assertEqual(first["amount"], 237500.00)
        self.assertIn("INV/2026/00004", first["payment_ref"])   # a wrapped description is joined
        self.assertEqual(parsed["transactions"][1]["amount"], -52.50)

    def test_refuses_a_statement_that_does_not_add_up(self):
        broken = self._sample().replace(b"3,580,854.73", b"3,580,854.74")
        if broken == self._sample():
            self.skipTest("closing balance not stored as plain text in this PDF")
        with self.assertRaises(StatementError):
            parse_statement(broken)
