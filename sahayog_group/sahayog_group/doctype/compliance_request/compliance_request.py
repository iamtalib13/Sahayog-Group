# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import (
    add_days, add_months, add_to_date, escape_html, get_url_to_form, getdate, nowdate, now_datetime,
)


MASTER_DOCTYPE = "Compliance"
RULE_DOCTYPE = "Compliance"

COMPLETED = "Closed / Completed"
SUBMITTED = "Completion Submitted"
CLOSURE_STATUSES = (SUBMITTED, COMPLETED)

RECURRENCE_MONTHS = {
    "Monthly": 1,
    "Quarterly": 3,
    "Half-Yearly": 6,
    "Yearly": 12,
}


class ComplianceRequest(Document):
    def validate(self):
        self.set_from_rule()
        self.set_original_due_date()
        self.set_start_date()
        self.populate_evidence_rows()
        self.stamp_evidence_uploader()
        self.handle_resubmission()
        self.handle_rejection()
        self.validate_maker_checker()
        self.validate_evidence_complete()
        self.validate_approval()
        self.validate_status_requirements()
        self.validate_dates()
        self.validate_baseline_evidence_rows()
        self.validate_duplicate()
        self.set_closure_details()

    def on_update(self):
        self.create_next_cycle()

    # ---------- helpers ----------
    def block(self, message):
        """Stop the action and write the blocked attempt to a log file (BRD 8.2)."""
        frappe.logger("compliance_closure").warning(
            f"{self.name or 'new'} | user={frappe.session.user} | status={self.status} | {message}"
        )
        frappe.throw(message, title=_("Action Blocked"))

    def requires_maker_checker(self):
        return self.risk_tier == "Critical"

    # ---------- Rule ----------
    def set_from_rule(self):
        """Everything about the obligation comes from the Compliance."""
        if not self.compliance or not frappe.db.exists(RULE_DOCTYPE, self.compliance):
            return
        rule = frappe.db.get_value(
            RULE_DOCTYPE, self.compliance,
            ["category", "department", "company", "project", "risk_tier"],
            as_dict=True,
        )
        if not rule:
            return
        for f in ("category", "department", "company", "project", "risk_tier"):
            if rule.get(f):
                self.set(f, rule.get(f))

        # Fetch role assignments from Compliance Assignment Item
        assignments = frappe.get_all(
            "Compliance Assignment Item",
            filters={"parent": self.compliance, "parenttype": RULE_DOCTYPE},
            fields=["role", "user"],
        )
        role_map = {
            "Responsible Person": "responsible_person",
            "Backup Owner": "backup_owner",
            "Reviewer": "reviewer",
            "Department Head": "department_head",
            "Unit Head": "unit_head",
            "Central Compliance Owner": "central_compliance_owner",
        }
        for row in assignments:
            field = role_map.get(row.role)
            if field and not self.get(field):
                self.set(field, row.user)

    # ---------- dates ----------
    def set_original_due_date(self):
        if self.due_date and not self.original_due_date:
            self.original_due_date = self.due_date

    def set_start_date(self):
        """Stamp the day work actually began (first time the status moves past not-started)."""
        started = (
            "In Progress", "Application Submitted", "Awaiting Authority / Third Party",
            "Blocked / At Risk", "Completion Submitted", "Closed / Completed",
        )
        if self.status in started:
            if not self.start_date:
                self.start_date = nowdate()
            if not self.initiation_date:
                self.initiation_date = nowdate()

    # ---------- evidence rows ----------
    def populate_evidence_rows(self):
        if not self.is_new() or self.evidence_items or not self.compliance:
            return
        if not frappe.db.exists(MASTER_DOCTYPE, self.compliance):
            return
        master = frappe.get_doc(MASTER_DOCTYPE, self.compliance)
        for rule in master.evidence_rules:
            self.append("evidence_items", {
                "evidence_type": rule.evidence_type,
                "is_mandatory": rule.is_mandatory,
                "is_payment_proof": rule.is_payment_proof,
            })

    def stamp_evidence_uploader(self):
        """Auto-stamp uploaded_by + uploaded_at on evidence rows that have a file but no uploader (BRD FR-13, Sec-7)."""
        for row in self.evidence_items:
            if row.file and not row.uploaded_by:
                row.uploaded_by = frappe.session.user
                row.uploaded_at = now_datetime()

    # ---------- review flow ----------
    def handle_resubmission(self):
        """Owner submits for closure (again): clear the old decision."""
        if self.status == SUBMITTED and self.has_value_changed("status"):
            self.reviewer_decision = ""
            self.completion_requested_on = nowdate()

    def handle_rejection(self):
        """Reviewer rejects: record goes back to the owner."""
        if self.reviewer_decision == "Rejected" and self.status in CLOSURE_STATUSES:
            self.status = "In Progress"
            frappe.msgprint(
                _("Closure rejected. The record is back with the Responsible Person (In Progress)."),
                indicator="orange",
            )

    def validate_maker_checker(self):
        # Critical records: Reviewer must be a different person
        if (
            self.requires_maker_checker()
            and self.reviewer
            and self.reviewer == self.responsible_person
        ):
            self.block(_("For Risk Tier {0} the Reviewer must be a different person from the Responsible Person.").format(self.risk_tier))

        # Only the assigned Reviewer can close (Administrator is not exempt, BRD section 8)
        if self.status == COMPLETED and self.has_value_changed("status"):
            if frappe.session.user != self.reviewer:
                self.block(
                    _("Only the assigned Reviewer ({0}) can mark this record as Closed / Completed.").format(self.reviewer)
                )

    def validate_evidence_complete(self):
        if self.status not in CLOSURE_STATUSES:
            return
        missing = []
        for row in self.evidence_items:
            if not row.is_mandatory:
                continue
            gaps = []
            if not row.file:
                gaps.append(_("File"))
            if not row.document_date:
                gaps.append(_("Document Date"))
            if gaps:
                missing.append(f"<li>{row.evidence_type}: {', '.join(gaps)}</li>")
        if missing:
            self.block(_("Mandatory evidence is incomplete:") + "<ul>" + "".join(missing) + "</ul>")

    def validate_approval(self):
        if self.status == COMPLETED and self.reviewer_decision != "Approved":
            self.block(_("Reviewer Decision must be Approved before this record can be Closed / Completed."))

    def set_closure_details(self):
        if self.status == COMPLETED:
            if not self.closed_on:
                self.closed_on = now_datetime()
                self.closed_by = frappe.session.user
        else:
            self.closed_on = None
            self.closed_by = None

    # ---------- status rules ----------
    def validate_status_requirements(self):
        has_file = any(row.file for row in self.evidence_items)
        stop = lambda msg: frappe.throw(msg, title=_("Action Blocked"))

        if self.status == "Application Submitted":
            if not self.application_reference_no:
                stop(_("Application Reference No is required when the status is Application Submitted."))
            if not has_file:
                stop(_("Upload the official acknowledgement (at least one evidence file) before marking Application Submitted."))

        elif self.status == "Awaiting Authority / Third Party":
            if not self.next_follow_up_date:
                stop(_("Next Follow-up Date is required when the status is Awaiting Authority / Third Party."))
            if not has_file:
                stop(_("Upload the submission proof (at least one evidence file) before marking Awaiting Authority / Third Party."))

        elif self.status == "Blocked / At Risk":
            if not self.blocker:
                stop(_("Blocker is required when the status is Blocked / At Risk."))
            if not self.next_action:
                stop(_("Next Action (mitigation plan) is required when the status is Blocked / At Risk."))

    # ---------- date checks ----------
    def validate_dates(self):
        today = getdate(nowdate())
        for row in self.evidence_items:
            if row.document_date and getdate(row.document_date) > today:
                frappe.throw(_("Evidence row {0}: Document Date cannot be in the future.").format(row.idx))
            if row.expiry_date and row.document_date and getdate(row.expiry_date) < getdate(row.document_date):
                frappe.throw(_("Evidence row {0}: Expiry Date cannot be before the Document Date.").format(row.idx))

    # ---------- mandatory baseline evidence cannot be removed ----------
    def validate_baseline_evidence_rows(self):
        before = self.get_doc_before_save()
        if not before:
            return
        current = {row.name for row in self.evidence_items}
        removed = [r.evidence_type for r in before.evidence_items if r.is_mandatory and r.name not in current]
        if removed:
            frappe.throw(
                _("Mandatory evidence rows cannot be removed: {0}").format(", ".join(removed)),
                title=_("Action Blocked"),
            )

    # ---------- duplicates ----------
    def validate_duplicate(self):
        if not (self.compliance and self.due_date):
            return
        dup = frappe.db.exists(self.doctype, {
            "compliance": self.compliance,
            "due_date": self.due_date,
            "name": ["!=", self.name],
            "status": ["not in", [COMPLETED, "Superseded / Inactive"]],
        })
        if dup:
            frappe.throw(
                _("A similar open record already exists: {0}").format(dup),
                title=_("Duplicate Record"),
            )

    # ---------- next cycle ----------
    def create_next_cycle(self):
        # Only when the status has just become Closed / Completed
        before = self.get_doc_before_save()
        if self.status != COMPLETED or (before and before.status == COMPLETED):
            return

        recurrence = frappe.db.get_value(RULE_DOCTYPE, self.compliance, "recurrence")
        months = RECURRENCE_MONTHS.get(recurrence)
        if not months:
            return  # One-time compliance, no next cycle

        # Avoid duplicates
        if frappe.db.exists(self.doctype, {"previous_record": self.name}):
            return

        next_due = add_months(getdate(self.due_date), months)
        if frappe.db.exists(self.doctype, {
            "compliance": self.compliance,
            "due_date": next_due,
            "status": ["!=", "Superseded / Inactive"],
        }):
            return  # next cycle already created (e.g. by the daily auto-create job)

        frappe.get_doc({
            "doctype": self.doctype,
            "compliance": self.compliance,
            "responsible_person": self.responsible_person,
            "reviewer": self.reviewer,
            "department_head": self.department_head,
            "backup_owner": self.backup_owner,
            "due_date": next_due,
            "previous_record": self.name,
            "status": "Upcoming",
        }).insert(ignore_permissions=True)


# ======================= Action buttons (BRD 8.2, 10.3, 5.1, FR-20) =======================
REQUEST_DOCTYPE = "Compliance Request"
WORKING = ["In Progress", "Application Submitted", "Awaiting Authority / Third Party"]

ACTIONS = {
    "Start Work": {"from": ["Draft", "Upcoming", "Action Required"], "to": "In Progress", "by": "owner"},
    "Submit Application": {"from": ["In Progress"], "to": "Application Submitted", "by": "owner"},
    "Mark Awaiting Authority": {"from": ["Application Submitted"], "to": "Awaiting Authority / Third Party", "by": "owner"},
    "Mark Blocked": {"from": WORKING, "to": "Blocked / At Risk", "by": "owner"},
    "Resume Work": {"from": ["Blocked / At Risk"], "to": "In Progress", "by": "owner"},
    "Request Closure": {"from": WORKING, "to": SUBMITTED, "by": "owner"},
    "Approve": {"from": [SUBMITTED], "to": COMPLETED, "by": "reviewer"},
    "Reject": {"from": [SUBMITTED], "to": SUBMITTED, "by": "reviewer"},
    "Reopen": {"from": [COMPLETED], "to": "In Progress", "by": "manager"},
}


def _clean(value):
    return (value or "").strip()


@frappe.whitelist()
def run_action(name, action, reason=None, blocker=None, next_action=None):
    from frappe.utils import escape_html

    rule = ACTIONS.get(action)
    if not rule:
        frappe.throw(_("Unknown action: {0}").format(action))

    doc = frappe.get_doc(REQUEST_DOCTYPE, name)

    if doc.status not in rule["from"]:
        frappe.throw(_("'{0}' is not allowed when the status is {1}.").format(action, doc.status))

    allowed = {
        "owner": [doc.responsible_person, doc.backup_owner],
        "reviewer": [doc.reviewer],
        "manager": [doc.reviewer, doc.department_head],
    }[rule["by"]]
    if frappe.session.user not in [u for u in allowed if u]:
        frappe.throw(_("You are not allowed to do '{0}' on this record.").format(action))

    reason = _clean(reason)
    if action in ("Reject", "Reopen") and not reason:
        frappe.throw(_("A reason is required for '{0}'.").format(action))

    if action == "Mark Blocked":
        if not _clean(blocker) or not _clean(next_action):
            frappe.throw(_("Blocker and Next Action are required."))
        doc.blocker = _clean(blocker)
        doc.next_action = _clean(next_action)
    elif action == "Approve":
        doc.reviewer_decision = "Approved"
    elif action == "Reject":
        doc.reviewer_decision = "Rejected"
        doc.rejection_reason = reason
    elif action == "Reopen":
        doc.reviewer_decision = ""
        doc.restart_work_date = nowdate()

    doc.status = rule["to"]
    doc.flags.ignore_permissions = True
    doc.save()

    text = action + (": " + escape_html(reason) if reason else "")
    if action == "Mark Blocked":
        text += ": " + escape_html(doc.blocker)
    doc.add_comment("Comment", text)
    return doc.status


@frappe.whitelist()
def reassign(name, new_responsible, reason, new_backup=None):
    from frappe.utils import escape_html

    doc = frappe.get_doc(REQUEST_DOCTYPE, name)

    if doc.status in (COMPLETED, "Superseded / Inactive"):
        frappe.throw(_("A closed or superseded record cannot be reassigned."))
    if frappe.session.user != doc.department_head:
        frappe.throw(_("Only the Department Head can reassign this record."))
    if not _clean(reason):
        frappe.throw(_("A reason is required for reassignment."))
    if not frappe.db.get_value("User", new_responsible, "enabled"):
        frappe.throw(_("{0} is not an active user.").format(new_responsible))

    old_owner, old_backup = doc.responsible_person, doc.backup_owner
    doc.responsible_person = new_responsible
    if new_backup:
        doc.backup_owner = new_backup
    doc.flags.ignore_permissions = True
    doc.save()

    doc.add_comment(
        "Comment",
        "Reassigned: Responsible Person {0} -> {1}; Backup Owner {2} -> {3}. Reason: {4}".format(
            old_owner, doc.responsible_person, old_backup or "-", doc.backup_owner or "-", escape_html(_clean(reason))
        ),
    )
    _notify_reassignment(
        doc.name, old_owner, doc.responsible_person, doc.backup_owner, _clean(reason), frappe.session.user,
    )
    return doc.responsible_person


@frappe.whitelist()
def get_default_due_date(compliance=None, compliance_rule=None):
    compliance = compliance or compliance_rule
    """Due Date = Rule Start Date + Recurrence for the first Request,
    otherwise the latest Request's Due Date + Recurrence."""
    rule = frappe.db.get_value(RULE_DOCTYPE, compliance, ["start_date", "recurrence"], as_dict=True)
    if not rule or not rule.start_date:
        return None
    months = RECURRENCE_MONTHS.get(rule.recurrence)
    if not months:
        return None

    latest = frappe.get_all(
        REQUEST_DOCTYPE,
        filters={"compliance": compliance, "status": ["!=", "Superseded / Inactive"]},
        pluck="due_date", order_by="due_date desc", limit=1,
    )
    return add_months(getdate(latest[0] if latest else rule.start_date), months)


# ======================= Overdue auto-set scheduler (BRD FR-09, Sec-9, Sec-10.4) =======================

OPEN_STATUSES = [
    "Draft", "Upcoming", "Action Required", "In Progress",
    "Application Submitted", "Awaiting Authority / Third Party",
    "Blocked / At Risk", "Completion Submitted",
]


def check_and_set_overdue():
    """
    Daily job: flip status to 'Overdue' for any open record whose due_date has passed
    the grace period set in the Settings tab of its Compliance. Original due date is preserved. (BRD FR-09, Sec-9)
    """
    today = getdate(nowdate())
    candidates = frappe.get_all(
        REQUEST_DOCTYPE,
        filters={"status": ["in", OPEN_STATUSES], "due_date": ["<", today], "is_active": 1},
        fields=["name", "compliance", "due_date"],
    )
    done = []
    for r in candidates:
        cfg = _alert_config(r.compliance)
        grace = cfg["grace"] if cfg else 0
        cutoff = add_days(today, -grace)
        if getdate(r.due_date) < cutoff:
            frappe.db.set_value(REQUEST_DOCTYPE, r.name, "status", "Overdue", update_modified=False)
            _escalate_overdue(r.name)
            frappe.logger("compliance_overdue").info(f"{r.name} → Overdue (due_date < {cutoff})")
            done.append(r.name)

    if done:
        frappe.db.commit()

    return len(done)


# ======================= Alerts, acknowledgement and escalation (BRD FR-08, FR-09, Sec-11) =======================

ALERT_LOG = "Alert Log"
CEO_ROLE = "Compliance Executive"
TIERS = ("Critical", "High", "Medium", "Low")
URGENT_DAYS = 7
REQUEST_FIELDS = [
    "name", "compliance", "risk_tier", "status", "due_date", "responsible_person", "backup_owner",
    "reviewer", "department_head", "unit_head", "central_compliance_owner",
]


def _compliance_title(rec):
    return frappe.db.get_value("Compliance", rec.get("compliance"), "compliance") or rec.name


CHAIRMAN_OFFICE_ROLE = "Compliance Monitor"


def _alert_config(compliance):
    """Alert settings of one Compliance (its Settings tab Escalation Ladder)."""
    if not compliance or not frappe.db.exists("Compliance", compliance):
        return None
    c = frappe.get_cached_doc("Compliance", compliance)
    ladder = []
    for r in (c.get("alert_days") or []):
        offset = (r.offset_type or "Before Due Date").strip()
        days = int(r.days or 0)
        if offset == "On Due Date":
            days = 0
        ladder.append({
            "offset_type": offset,
            "days": days,
            "responsible": bool(r.get("notify_responsible")),
            "dept_head": bool(r.get("notify_dept_head")),
            "unit_head": bool(r.get("notify_unit_head")),
            "reviewer": bool(r.get("notify_reviewer")),
            "central_owner": bool(r.get("notify_central_owner")),
            "ceo": bool(r.get("notify_ceo")),
            "chairmans_office": bool(r.get("notify_chairmans_office")),
            "urgent": bool(r.get("is_urgent")),
        })
    return {
        "ladder": ladder,
        "grace": int(c.get("overdue_grace_days") or 0),
        "window": int(c.get("acknowledgement_window_days") or 2),
    }


def _users_with_role(role):
    return frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent")


def _clean_users(users):
    """Remove blanks, duplicates, disabled users and system users."""
    seen, result = set(), []
    for u in users:
        if not u or u in seen or u in ("Administrator", "Guest"):
            continue
        if frappe.db.get_value("User", u, "enabled"):
            seen.add(u)
            result.append(u)
    return result


def _ladder_step_recipients(rec, step):
    """Resolve recipients for a specific ladder step."""
    users = []
    if step.get("responsible"):
        users.append(rec.get("responsible_person"))
        if rec.get("backup_owner"):
            users.append(rec.get("backup_owner"))
    if step.get("dept_head"):
        users.append(rec.get("department_head"))
    if step.get("unit_head"):
        users.append(rec.get("unit_head"))
    if step.get("reviewer"):
        users.append(rec.get("reviewer"))
    if step.get("central_owner"):
        users.append(rec.get("central_compliance_owner"))
    if step.get("ceo"):
        users += _users_with_role(CEO_ROLE)
    if step.get("chairmans_office"):
        users += _users_with_role(CHAIRMAN_OFFICE_ROLE)
        users += _users_with_role("Compliance Chairman")
        users += _users_with_role("Compliance Viewer")
    return _clean_users(users)


def _open_requests(extra):
    filters = {"status": ["in", OPEN_STATUSES], "is_active": 1}
    filters.update(extra)
    return frappe.get_all(REQUEST_DOCTYPE, filters=filters, fields=REQUEST_FIELDS)


def _already_logged(request, user, alert_type, days_before=0):
    return frappe.db.exists(ALERT_LOG, {
        "compliance_request": request, "recipient": user,
        "alert_type": alert_type, "days_before": days_before,
    })


def _alert_content(rec, alert_type, days_before, urgent, note=None):
    title = _compliance_title(rec)
    prefix = _("URGENT: ") if urgent else ""
    if alert_type == "Due Soon":
        subject = _("{0}Compliance Alert: {1} due in {2} day(s) [{3}]").format(prefix, title, days_before, rec.risk_tier)
        intro = _("This compliance is due in {0} day(s).").format(days_before)
    elif alert_type == "Due Date":
        subject = _("{0}Compliance due today: {1} [{2}]").format(prefix, title, rec.risk_tier)
        intro = _("This compliance is due today and is not yet complete.")
    elif alert_type == "Overdue":
        if days_before > 0:
            subject = _("{0}Compliance OVERDUE ({1} days): {2} [{3}]").format(prefix, days_before, title, rec.risk_tier)
            intro = _("This compliance is overdue by {0} day(s). Please follow up immediately.").format(days_before)
        else:
            subject = _("{0}Compliance OVERDUE: {1} [{2}]").format(prefix, title, rec.risk_tier)
            intro = _("This compliance is overdue. Please follow up immediately.")
    elif alert_type == "Reassignment":
        subject = _("Compliance reassigned: {0} [{1}]").format(title, rec.risk_tier)
        intro = _("This compliance record has been reassigned.")
    else:
        subject = _("{0}Escalation: {1} [{2}]").format(prefix, title, rec.risk_tier)
        intro = _("This alert has been escalated to you.")
    note_html = f"<p>{escape_html(note)}</p>" if note else ""
    url = get_url_to_form(REQUEST_DOCTYPE, rec.name)
    due = frappe.format(rec.due_date, {"fieldtype": "Date"}) if rec.due_date else "-"
    message = f"""
        <p>{escape_html(intro)}</p>{note_html}
        <table style="border-collapse:collapse;">
          <tr><td style="padding:4px 8px;"><b>Record</b></td><td><a href="{url}">{rec.name}</a></td></tr>
          <tr><td style="padding:4px 8px;"><b>Compliance</b></td><td>{escape_html(title)}</td></tr>
          <tr><td style="padding:4px 8px;"><b>Due Date</b></td><td>{due}</td></tr>
          <tr><td style="padding:4px 8px;"><b>Status</b></td><td>{rec.status}</td></tr>
          <tr><td style="padding:4px 8px;"><b>Risk Tier</b></td><td>{rec.risk_tier}</td></tr>
        </table>
        <p>Open the record and click <b>Acknowledge Alert</b> to confirm you have seen this.</p>
    """
    return subject, message


def _send_alert(rec, user, alert_type, days_before=0, urgent=False, note=None, escalated_from=None):
    """Email one person and write the Alert Log row (who, when, Sent / Failed)."""
    log = frappe.get_doc({
        "doctype": ALERT_LOG,
        "compliance_request": rec.name,
        "recipient": user,
        "alert_type": alert_type,
        "days_before": days_before,
        "sent_on": now_datetime(),
        "delivery_status": "Failed",
        "escalated_from": escalated_from,
    })
    email = frappe.db.get_value("User", user, "email")
    if not email:
        log.failure_reason = _("The user has no email address.")
    else:
        subject, message = _alert_content(rec, alert_type, days_before, urgent, note)
        try:
            frappe.sendmail(
                recipients=[email], subject=subject, message=message,
                reference_doctype=REQUEST_DOCTYPE, reference_name=rec.name, now=True,
            )
            log.delivery_status = "Sent"
        except Exception as e:
            log.failure_reason = str(e)[:500]
            frappe.logger("compliance_alerts").error(f"Alert FAILED: {rec.name} | {alert_type} | {user} | {e}")
    log.insert(ignore_permissions=True)
    return log


def send_compliance_alerts():
    """
    Daily job: evaluate Escalation Ladder steps from the Settings tab of each Compliance.
    Handles 'Before Due Date', 'On Due Date', and 'After Due Date' triggers.
    Each recipient gets an alert at most once per trigger step.
    """
    today = getdate(nowdate())
    count = 0

    open_requests = frappe.get_all(
        REQUEST_DOCTYPE,
        filters={"status": ["in", OPEN_STATUSES + ["Overdue"]], "is_active": 1},
        fields=REQUEST_FIELDS,
    )

    for rec in open_requests:
        if not rec.due_date:
            continue
        cfg = _alert_config(rec.compliance)
        if not cfg or not cfg.get("ladder"):
            continue

        due_date = getdate(rec.due_date)
        diff_days = (due_date - today).days  # > 0 means before, == 0 means on due date, < 0 means after due date

        for step in cfg["ladder"]:
            offset_type = step.get("offset_type")
            step_days = step.get("days", 0)
            should_fire = False
            alert_type = "Due Soon"
            logged_day = step_days

            if offset_type == "Before Due Date" and diff_days > 0 and diff_days == step_days:
                should_fire = True
                alert_type = "Due Soon"
                logged_day = step_days
            elif offset_type == "On Due Date" and diff_days == 0:
                should_fire = True
                alert_type = "Due Date"
                logged_day = 0
            elif offset_type == "After Due Date" and diff_days < 0 and abs(diff_days) == step_days:
                should_fire = True
                alert_type = "Overdue"
                logged_day = step_days

            if not should_fire:
                continue

            urgent = step.get("urgent") or (alert_type in ("Due Date", "Overdue"))
            for user in _ladder_step_recipients(rec, step):
                if not _already_logged(rec.name, user, alert_type, logged_day):
                    _send_alert(rec, user, alert_type, logged_day, urgent=urgent)
                    count += 1

    if count:
        frappe.db.commit()
    return count


def _escalate_overdue(name):
    """Called when status flips to Overdue: notify recipients configured in overdue ladder steps or central owner."""
    try:
        rec = frappe.db.get_value(REQUEST_DOCTYPE, name, REQUEST_FIELDS, as_dict=True)
        if not rec:
            return
        cfg = _alert_config(rec.compliance)
        notified = False
        if cfg and cfg.get("ladder"):
            for step in cfg["ladder"]:
                if step.get("offset_type") == "After Due Date":
                    for user in _ladder_step_recipients(rec, step):
                        if not _already_logged(rec.name, user, "Overdue", step.get("days", 0)):
                            _send_alert(rec, user, "Overdue", step.get("days", 0), urgent=True)
                            notified = True
        if not notified:
            # Fallback if no After Due Date step configured yet
            users = _clean_users([rec.responsible_person, rec.department_head, rec.unit_head, rec.central_compliance_owner])
            for user in users:
                if not _already_logged(rec.name, user, "Overdue", 0):
                    _send_alert(rec, user, "Overdue", 0, urgent=True)
    except Exception as e:
        frappe.logger("compliance_alerts").error(f"Overdue escalation FAILED: {name} | {e}")


def _manager_for(rec, recipient):
    """Owner's manager: Department Head, then Unit Head, then Central Compliance Owner (the next one above the recipient)."""
    chain = ["department_head", "unit_head", "central_compliance_owner"]
    start = 0
    for i, field in enumerate(chain):
        if rec.get(field) == recipient:
            start = i + 1
    for field in chain[start:]:
        user = rec.get(field)
        if user and user != recipient and _clean_users([user]):
            return user
    return None


def escalate_unacknowledged_alerts():
    """Daily job: an alert not acknowledged within the window of its Compliance goes to the owner's manager (BRD section 11)."""
    now = now_datetime()
    pending = frappe.get_all(
        ALERT_LOG,
        filters={"acknowledged": 0, "escalated": 0, "alert_type": ["not in", ["Escalation", "Reassignment"]]},
        fields=["name", "compliance_request", "recipient", "alert_type", "sent_on"],
    )
    count = 0
    for row in pending:
        rec = frappe.db.get_value(REQUEST_DOCTYPE, row.compliance_request, REQUEST_FIELDS, as_dict=True)
        if not rec or rec.status not in OPEN_STATUSES + ["Overdue"]:
            continue
        cfg = _alert_config(rec.compliance)
        window = cfg["window"] if cfg else 2
        if not row.sent_on or row.sent_on >= add_to_date(now, days=-window):
            continue
        manager = _manager_for(rec, row.recipient)
        if not manager:
            continue
        note = _("{0} has not acknowledged the earlier {1} alert.").format(row.recipient, row.alert_type)
        _send_alert(rec, manager, "Escalation", 0, urgent=True, note=note, escalated_from=row.name)
        frappe.db.set_value(ALERT_LOG, row.name, {"escalated": 1, "escalated_on": now_datetime()})
        count += 1

    if count:
        frappe.db.commit()
    return count


def _notify_reassignment(name, old_owner, new_owner, new_backup, reason, by):
    """Tell the new owner, the new backup and the previous owner (mail + Alert Log row of type Reassignment)."""
    try:
        rec = frappe.db.get_value(REQUEST_DOCTYPE, name, REQUEST_FIELDS, as_dict=True)
        if not rec:
            return
        note = _("Reassigned by {0}: Responsible Person {1} -> {2}. Reason: {3}").format(
            by, old_owner or "-", new_owner, reason
        )
        for user in _clean_users([new_owner, new_backup, old_owner]):
            _send_alert(rec, user, "Reassignment", 0, False, note)
    except Exception as e:
        frappe.logger("compliance_alerts").error(f"Reassignment mail FAILED: {name} | {e}")


@frappe.whitelist()
def get_pending_alert_count(name):
    frappe.has_permission(REQUEST_DOCTYPE, "read", name, throw=True)
    return frappe.db.count(ALERT_LOG, {"compliance_request": name, "recipient": frappe.session.user, "acknowledged": 0})


@frappe.whitelist()
def acknowledge_alerts(name):
    """The logged-in user confirms they have seen the alerts sent to them for this Request."""
    frappe.has_permission(REQUEST_DOCTYPE, "read", name, throw=True)
    rows = frappe.get_all(
        ALERT_LOG,
        filters={"compliance_request": name, "recipient": frappe.session.user, "acknowledged": 0},
        pluck="name",
    )
    for row in rows:
        frappe.db.set_value(ALERT_LOG, row, {"acknowledged": 1, "acknowledged_on": now_datetime()})
    if rows:
        frappe.get_doc(REQUEST_DOCTYPE, name).add_comment("Comment", f"Alert acknowledged by {frappe.session.user}")
    return len(rows)
