import frappe
from frappe import _
from frappe.model.document import Document


class ComplianceProject(Document):
    def validate(self):
        self.project = (self.project or "").strip()
        exists = frappe.db.exists("Compliance Project", {
            "project": self.project,
            "company": self.company,
            "name": ["!=", self.name],
        })
        if exists:
            frappe.throw(
                _("Project {0} already exists for Company {1}.").format(self.project, self.company)
            )
