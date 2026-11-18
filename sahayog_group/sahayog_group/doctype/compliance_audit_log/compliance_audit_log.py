import frappe
from frappe import _
from frappe.model.document import Document


class ComplianceAuditLog(Document):
    """Append-only: entries can be created by the system, never edited or deleted (BRD section 15)."""

    def before_save(self):
        if not self.is_new():
            frappe.throw(_("Audit entries cannot be changed."))

    def on_trash(self):
        if not (frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_test):
            frappe.throw(_("Audit entries cannot be deleted."))

