"""BRD section 5: roles. Created on every migrate; roles are given to people from the assignments made in the masters."""

import frappe

ROLES = [
    "Compliance Master Admin",       # Master Administrator
    "Compliance Chairman",           # Chairman / Promoter
    "Compliance Executive",          # CEO
    "Compliance Viewer",                # CCC Committee and Chairman's Office
    "Compliance Coordinator",      # Central Compliance Owner / Coordinator
    "Compliance Operations Head",    # Central Hospital Management / Operations Head
    "Compliance Facility Head",          # Unit Head / Hospital Head
    "Compliance Department Head",    # Department Head
    "Compliance User", # Responsible Person / Compliance Owner
    "Compliance Checker",           # Evidence Reviewer / Approver
    "Compliance Auditor",            # Auditor / Read-only Reviewer
    "Compliance Project Head",       # Project Head
]

# doctype -> [(field, role)]
AUTO_ROLES = {
    "Compliance": [
        ("responsible_person", "Compliance User"),
        ("backup_owner", "Compliance User"),
        ("reviewer", "Compliance Checker"),
        ("department_head", "Compliance Department Head"),
        ("unit_head", "Compliance Facility Head"),
        ("central_compliance_owner", "Compliance Coordinator"),
    ],
    "Compliance Department": [("department_head", "Compliance Department Head")],
    "Compliance Project": [("project_head", "Compliance Project Head")],
}


def setup_roles():
    for role in ROLES:
        if not frappe.db.exists("Role", role):
            frappe.get_doc({"doctype": "Role", "role_name": role, "desk_access": 1}).insert(ignore_permissions=True)
    for doctype, pairs in AUTO_ROLES.items():
        for name in frappe.get_all(doctype, pluck="name"):
            _grant_from(frappe.get_doc(doctype, name), pairs)
    frappe.db.commit()


def _grant(user, role):
    if not user or user in ("Administrator", "Guest"):
        return
    if not frappe.db.get_value("User", user, "enabled"):
        return
    if frappe.db.exists("Has Role", {"parent": user, "parenttype": "User", "role": role}):
        return
    frappe.get_doc({
        "doctype": "Has Role", "parent": user, "parenttype": "User", "parentfield": "roles", "role": role,
    }).insert(ignore_permissions=True)
    frappe.clear_cache(user=user)


def _grant_from(doc, pairs):
    for field, role in pairs:
        _grant(doc.get(field), role)


def sync_roles_for_doc(doc, method=None):
    """doc_events hook: whoever is named as owner / reviewer / head in a master gets the matching role."""
    try:
        _grant_from(doc, AUTO_ROLES.get(doc.doctype, []))
    except Exception:
        frappe.log_error(title="Compliance role sync failed: {0} {1}".format(doc.doctype, doc.name))


def check_users():
    """Read-only: print the Compliance roles (and System Manager) of every active user."""
    for user in frappe.get_all("User", filters={"enabled": 1, "user_type": "System User"}, pluck="name"):
        roles = [x for x in frappe.get_roles(user) if x.startswith("Compliance") or x == "System Manager"]
        print(user, "->", roles)


def remove_system_manager(users):
    """Take System Manager away from the given users only (so they see only what their Compliance roles allow)."""
    for user in users:
        if user in ("Administrator", "Guest"):
            print("skipped", user)
            continue
        for row in frappe.get_all("Has Role", filters={"parent": user, "parenttype": "User", "role": "System Manager"}, pluck="name"):
            frappe.delete_doc("Has Role", row, ignore_permissions=True, force=True)
        frappe.clear_cache(user=user)
        print("System Manager removed from", user)
    frappe.db.commit()
