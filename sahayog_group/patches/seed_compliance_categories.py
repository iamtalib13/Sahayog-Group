import frappe

def execute():
    """Seed standard BRD Compliance Categories including Rent & Lease."""
    categories = [
        {"category": "Hospital / Establishment Licences", "description": "Applicable hospital/clinical establishment registration, local permissions and renewal requirements."},
        {"category": "Fire and Building Safety", "description": "Fire safety approval/NOC, occupancy-related documents, lift inspection where applicable."},
        {"category": "Biomedical Waste / Environment", "description": "Applicable biomedical waste authorisation, waste collection agreement, manifests and related records."},
        {"category": "Pharmacy / Laboratory / Special Services", "description": "Pharmacy licence, laboratory or blood bank permissions and service-specific approvals where applicable."},
        {"category": "Professional Registrations", "description": "Doctor, nurse and other regulated professional registrations; credential validity."},
        {"category": "HR / Labour / Workplace", "description": "Applicable employment registrations, statutory filings, workplace or staff-related compliance."},
        {"category": "Finance / Tax", "description": "GST returns and registrations, TDS or other applicable filings, statutory payments and insurance."},
        {"category": "Contracts / Agreements", "description": "Doctor agreements, consultant contracts, vendor MOUs, outsourced agencies, leases, service agreements."},
        {"category": "Critical Services / Supplies", "description": "Medical gas/oxygen arrangements, biomedical waste collection, critical equipment maintenance and other material service dependencies."},
        {"category": "IT / Digital Continuity", "description": "Domain renewal, DNS, website hosting, SSL/TLS certificates, essential software subscriptions and backups."},
        {"category": "Insurance / Risk Transfer", "description": "Applicable hospital, property, professional indemnity, equipment or other insurance policies."},
        {"category": "Project / Pre-Opening Approvals", "description": "Construction-related approvals, occupancy/readiness approvals, service-specific licences, equipment and facility inspections."},
        {"category": "Rent & Lease", "description": "Property leases, land agreements, rental commitments and premise tenure renewals."},
        {"category": "Other / Organisation-Specific", "description": "Any additional obligation approved by the Master Administrator and validated by the compliance owner."}
    ]

    for cat in categories:
        if not frappe.db.exists("Compliance Category", cat["category"]):
            doc = frappe.get_doc({
                "doctype": "Compliance Category",
                "category": cat["category"],
                "description": cat["description"],
                "is_active": 1
            })
            doc.insert(ignore_permissions=True)

    frappe.db.commit()
