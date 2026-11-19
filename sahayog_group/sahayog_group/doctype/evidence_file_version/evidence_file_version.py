import frappe
from frappe import _
from frappe.model.document import Document


class EvidenceFileVersion(Document):
    """Older versions of an evidence file. Kept for ever; cannot be edited or deleted (BRD FR-13)."""

    def before_save(self):
        if not self.is_new():
            frappe.throw(_("Evidence versions cannot be changed."))

    def on_trash(self):
        if not (frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_test):
            frappe.throw(_("Evidence versions cannot be deleted."))

