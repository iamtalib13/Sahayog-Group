import frappe

def execute():
    """Seed standard Compliance Companies (Accumedix, Bank, Hospital)."""
    companies = [
        {"company": "Accumedix", "description": "Accumedix", "is_active": 1},
        {"company": "Bank", "description": "Bank", "is_active": 1},
        {"company": "Hospital", "description": "Hospital", "is_active": 1}
    ]

    for comp in companies:
        if not frappe.db.exists("Compliance Company", comp["company"]):
            doc = frappe.get_doc({
                "doctype": "Compliance Company",
                "company": comp["company"],
                "description": comp["description"],
                "is_active": comp["is_active"]
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
