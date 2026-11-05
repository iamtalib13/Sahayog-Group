from frappe.model.document import Document


class AlertDay(Document):
    def autoname(self):
        self.name = str(self.days)
