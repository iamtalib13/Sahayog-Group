"""Audit trail helper (BRD FR-14, section 8.2). Entries are append-only (see Compliance Audit Log)."""

import re

import frappe
from frappe.utils import now_datetime

AUDIT_LOG = "Compliance Audit Log"


def _plain(text):
    return re.sub(r"<[^>]+>", " ", str(text or "")).strip()[:1000]


def log_event(event, ref_doctype, ref_name, request=None, old=None, new=None, reason=None,
              details=None, commit=False, user=None):
    """Write one audit entry. Never breaks the business action if the log itself fails."""
    try:
        doc = frappe.get_doc({
            "doctype": AUDIT_LOG,
            "event_type": event,
            "event_time": now_datetime(),
            "user": user or frappe.session.user,
            "reference_doctype": ref_doctype,
            "reference_name": ref_name,
            "compliance_request": request,
            "old_value": _plain(old) if old not in (None, "") else None,
            "new_value": _plain(new) if new not in (None, "") else None,
            "reason": _plain(reason) if reason else None,
            "details": _plain(details) if details else None,
        })
        doc.flags.ignore_permissions = True
        doc.flags.ignore_links = True
        doc.insert()
        if commit:
            frappe.db.commit()
    except Exception:
        frappe.log_error(title="Compliance audit log failed")

