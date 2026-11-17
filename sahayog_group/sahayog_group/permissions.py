"""Scope rules (BRD section 5): role + scope. Group roles see everything; the others see only their own records."""

import frappe

GROUP_ROLES = {
    "System Manager", "Compliance Master Admin", "Compliance Chairman", "Compliance Executive",
    "Compliance Viewer", "Compliance Coordinator", "Compliance Operations Head", "Compliance Auditor",
}
# role -> fields on Compliance / Compliance Request that tie a person to a record
OWN_FIELDS = {
    "Compliance User": ("responsible_person", "backup_owner"),
    "Compliance Checker": ("reviewer",),
    "Compliance Department Head": ("department_head",),
    "Compliance Facility Head": ("unit_head",),
}


def _is_group(user):
    return user == "Administrator" or bool(GROUP_ROLES & set(frappe.get_roles(user)))


def _conditions(doctype, user):
    user = user or frappe.session.user
    if _is_group(user):
        return ""
    roles = set(frappe.get_roles(user))
    esc = frappe.db.escape(user)
    table = "`tab{0}`".format(doctype)
    parts = []
    for role, fields in OWN_FIELDS.items():
        if role in roles:
            parts += ["{0}.{1} = {2}".format(table, f, esc) for f in fields]
    if "Compliance Project Head" in roles:
        parts.append("{0}.project in (select name from `tabCompliance Project` where project_head = {1})".format(table, esc))
    return "(" + " or ".join(parts) + ")" if parts else "1 = 0"


def request_conditions(user=None):
    return _conditions("Compliance Request", user)


def compliance_conditions(user=None):
    return _conditions("Compliance", user)


def project_conditions(user=None):
    user = user or frappe.session.user
    if _is_group(user):
        return ""
    if "Compliance Project Head" in set(frappe.get_roles(user)):
        return "`tabCompliance Project`.project_head = {0}".format(frappe.db.escape(user))
    return "1 = 0"


def alert_log_conditions(user=None):
    user = user or frappe.session.user
    if _is_group(user):
        return ""
    esc = frappe.db.escape(user)
    own = "`tabAlert Log`.recipient = {0}".format(esc)
    req = _conditions("Compliance Request", user)
    if req and req != "1 = 0":
        own = "({0} or `tabAlert Log`.compliance_request in (select name from `tabCompliance Request` where {1}))".format(own, req)
    return own


def has_permission(doc, ptype=None, user=None, debug=False):
    """Document level check: opening a record that is outside the user's scope is denied."""
    user = user or frappe.session.user
    if _is_group(user) or ptype == "create" or doc.is_new():
        return True
    roles = set(frappe.get_roles(user))
    for role, fields in OWN_FIELDS.items():
        if role in roles and any(doc.get(f) == user for f in fields):
            return True
    if "Compliance Project Head" in roles and doc.get("project"):
        if frappe.db.get_value("Compliance Project", doc.get("project"), "project_head") == user:
            return True
    return False


def project_has_permission(doc, ptype=None, user=None, debug=False):
    user = user or frappe.session.user
    if _is_group(user) or ptype == "create" or doc.is_new():
        return True
    return "Compliance Project Head" in set(frappe.get_roles(user)) and doc.get("project_head") == user
