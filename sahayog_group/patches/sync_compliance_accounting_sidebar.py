import frappe

def execute():
	"""Sync updated Compliance MS sidebar containing accounting links."""
	if frappe.db.exists("DocType", "Sidebar"):
		frappe.reload_doc("sahayog_group", "sidebar", "compliance_ms", force=True)
