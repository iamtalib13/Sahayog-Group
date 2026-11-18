# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class ComplianceDepartment(Document):
	def on_update(self):
		"""When the Department Head changes, update the Compliances and the open Requests of this department."""
		before = self.get_doc_before_save()
		if not before or before.department_head == self.department_head:
			return
		head = self.department_head
		for name in frappe.get_all("Compliance", filters={"department": self.name}, pluck="name"):
			frappe.db.set_value("Compliance", name, "department_head", head, update_modified=False)
			rows = frappe.get_all(
				"Compliance Assignment Item",
				filters={"parent": name, "parenttype": "Compliance", "role": "Department Head"},
				pluck="name",
			)
			if rows:
				for row in rows:
					frappe.db.set_value("Compliance Assignment Item", row, "user", head, update_modified=False)
			else:
				doc = frappe.get_doc("Compliance", name)
				doc.append("assignments", {"role": "Department Head", "user": head})
				doc.flags.ignore_validate = True
				doc.save(ignore_permissions=True)
		for name in frappe.get_all(
			"Compliance Request",
			filters={"department": self.name, "status": ["not in", ["Closed / Completed", "Superseded / Inactive"]]},
			pluck="name",
		):
			frappe.db.set_value("Compliance Request", name, "department_head", head, update_modified=False)
