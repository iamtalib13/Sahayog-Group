import frappe

def execute():
	"""Sync Compliance MS sidebar with Cost Center link."""
	if frappe.db.exists("DocType", "Sidebar"):
		frappe.reload_doc("sahayog_group", "sidebar", "compliance_ms", force=True)
