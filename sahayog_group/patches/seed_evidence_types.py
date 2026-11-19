import frappe

def execute():
    """Seed standard BRD Evidence Types."""
    evidence_types = [
        {
            "type_name": "Licence / Certificate",
            "description": "Renewed licence, certificate, or official renewal confirmation issued by the authority.",
            "is_active": 1,
        },
        {
            "type_name": "Authority Acknowledgement / ARN",
            "description": "Official application acknowledgement, reference number (ARN), or receipt when final issuance is awaited.",
            "is_active": 1,
        },
        {
            "type_name": "Payment Receipt / Challan",
            "description": "Official treasury/bank challan, payment transaction receipt or bank acknowledgement.",
            "is_active": 1,
        },
        {
            "type_name": "Filing Acknowledgement",
            "description": "Statutory return filing confirmation, ARN, or official portal submission acknowledgement.",
            "is_active": 1,
        },
        {
            "type_name": "Executed Agreement / Addendum",
            "description": "Signed and executed contract, addendum, lease agreement, or authorised renewal confirmation.",
            "is_active": 1,
        },
        {
            "type_name": "Inspection / Service Report",
            "description": "Signed inspection/service report, calibration certificate, or maintenance completion sign-off.",
            "is_active": 1,
        },
        {
            "type_name": "Subscription / Domain Confirmation",
            "description": "Registrar invoice/receipt, DNS/SSL renewed validity confirmation, or SaaS subscription receipt.",
            "is_active": 1,
        },
        {
            "type_name": "Interim NOC / Official Communication",
            "description": "Interim NOC, project approval letter, or official regulatory correspondence.",
            "is_active": 1,
        },
    ]

    for et in evidence_types:
        if not frappe.db.exists("Evidence Type", et["type_name"]):
            doc = frappe.get_doc({
                "doctype": "Evidence Type",
                "type_name": et["type_name"],
                "description": et["description"],
                "is_active": et["is_active"],
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
