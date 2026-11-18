"""Part 1 of the BRD completion: audit trail, evidence version history, evidence access log (BRD FR-13, FR-14, Sec 8.2, Sec 15)."""

import frappe
from frappe import _
from frappe.utils import add_days, cint, now_datetime

from sahayog_group.sahayog_group.audit import log_event

REQUEST = "Compliance Request"
# roles allowed to remove an uploaded evidence row (BRD: deletion is restricted and audited)
MANAGER_ROLES = {"Compliance Master Admin", "Compliance Coordinator", "Compliance Operations Head", "System Manager"}


def request_validate(doc, method=None):
    """Uploaded evidence cannot be deleted by ordinary users; replacing a file needs a reason (BRD FR-13)."""
    before = doc.get_doc_before_save()
    if not before:
        return
    current = {r.name for r in doc.evidence_items}
    removed = [r for r in before.evidence_items if r.name not in current and r.file]
    if removed and not (set(frappe.get_roles()) & MANAGER_ROLES):
        doc.block(_("Uploaded evidence cannot be deleted. Only a Master Admin, Coordinator or Operations Head can remove it."))
    old = {r.name: r for r in before.evidence_items}
    for r in doc.evidence_items:
        o = old.get(r.name)
        if o and o.file and r.file and o.file != r.file and not (r.change_reason or "").strip():
            doc.block(_("Evidence row {0}: enter a Change Reason when replacing an uploaded file.").format(r.idx))


def request_on_update(doc, method=None):
    before = doc.get_doc_before_save()
    ref = (REQUEST, doc.name)
    if not before:
        log_event("Record Created", *ref, request=doc.name, new=doc.status)
        return
    if doc.status != before.status:
        if doc.status == "Completion Submitted":
            event = "Closure Requested"
        elif doc.status == "Closed / Completed":
            event = "Closed"
        elif before.status == "Closed / Completed":
            event = "Reopened"
        else:
            event = "Status Changed"
        log_event(event, *ref, request=doc.name, old=before.status, new=doc.status, reason=doc.status_reason)
    if doc.reviewer_decision == "Rejected" and before.reviewer_decision != "Rejected":
        log_event("Closure Rejected", *ref, request=doc.name, reason=doc.rejection_reason)
    for field, label in (("responsible_person", "Responsible Person"), ("backup_owner", "Backup Owner"), ("reviewer", "Reviewer")):
        if (doc.get(field) or "") != (before.get(field) or ""):
            log_event("Reassigned", *ref, request=doc.name, old=before.get(field), new=doc.get(field), details=label)
    if doc.due_date != before.due_date:
        log_event("Due Date Changed", *ref, request=doc.name, old=before.due_date, new=doc.due_date,
                  reason=doc.due_date_change_reason)
    _log_evidence(doc, before)


def _log_evidence(doc, before):
    old = {r.name: r for r in before.evidence_items}
    now_names = set()
    for r in doc.evidence_items:
        now_names.add(r.name)
        o = old.get(r.name)
        if r.file and (not o or not o.file):
            log_event("Evidence Uploaded", REQUEST, doc.name, request=doc.name, new=r.file, details=r.evidence_type)
        elif o and o.file and r.file != o.file:
            _keep_version(doc, o, "Replaced", r.change_reason)
            log_event("Evidence Replaced", REQUEST, doc.name, request=doc.name, old=o.file, new=r.file,
                      reason=r.change_reason, details=r.evidence_type)
            frappe.db.set_value("Evidence Item", r.name, "version_no", cint(o.version_no or 1) + 1, update_modified=False)
    for name, o in old.items():
        if name not in now_names and o.file:
            _keep_version(doc, o, "Removed", None)
            log_event("Evidence Removed", REQUEST, doc.name, request=doc.name, old=o.file, details=o.evidence_type)


def _keep_version(doc, row, action, reason):
    frappe.get_doc({
        "doctype": "Evidence File Version",
        "compliance_request": doc.name,
        "evidence_type": row.evidence_type,
        "version_no": cint(row.version_no or 1),
        "file": row.file,
        "document_date": row.document_date,
        "period": row.period,
        "action": action,
        "changed_by": frappe.session.user,
        "changed_on": now_datetime(),
        "reason": reason,
    }).insert(ignore_permissions=True)


@frappe.whitelist()
def log_evidence_access(name, file_url=None, action="Record Opened"):
    """Who opened a record's evidence (BRD Sec 15: record access to confidential evidence where feasible)."""
    frappe.has_permission(REQUEST, "read", name, throw=True)
    recent = frappe.db.sql(
        """select name from `tabCompliance Audit Log`
        where event_type = 'Evidence Accessed' and user = %s and reference_name = %s
        and ifnull(new_value, '') = %s and ifnull(details, '') = %s
        and event_time > date_sub(now(), interval 10 minute) limit 1""",
        (frappe.session.user, name, file_url or "", action),
    )
    if not recent:
        log_event("Evidence Accessed", REQUEST, name, request=name, new=file_url, details=action)
        frappe.db.commit()
    return 1

