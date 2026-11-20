import frappe


def execute():
	"""Sync Compliance MS workspace and sidebar in database."""
	if frappe.db.exists("DocType", "Sidebar"):
		frappe.reload_doc("sahayog_group", "sidebar", "compliance_ms", force=True)

	if frappe.db.exists("DocType", "Workspace"):
		frappe.reload_doc("sahayog_group", "workspace", "compliance_management", force=True)
