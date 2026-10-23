# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document


class Compliance(Document):
	def validate(self):
		self.is_critical = 1 if self.risk_tier == "Critical" else 0
