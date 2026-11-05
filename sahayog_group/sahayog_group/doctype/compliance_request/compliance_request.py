# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, getdate, nowdate, now_datetime


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
        self.set_started_on()
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
            ["category", "department", "company", "project", "risk_tier",
             "responsible_person", "backup_owner", "reviewer", "department_head"],
            as_dict=True,
        )
        if not rule:
            return
        for f in ("category", "department", "company", "project", "risk_tier"):
            if rule.get(f):
                self.set(f, rule.get(f))
        for f in ("responsible_person", "backup_owner", "reviewer", "department_head"):
            if not self.get(f):
                self.set(f, rule.get(f))

    # ---------- dates ----------
    def set_original_due_date(self):
        if self.due_date and not self.original_due_date:
            self.original_due_date = self.due_date

    def set_started_on(self):
        """Stamp the day work actually began (first time the status moves past not-started)."""
        started = (
            "In Progress", "Application Submitted", "Awaiting Authority / Third Party",
            "Blocked / At Risk", "Completion Submitted", "Closed / Completed",
        )
        if self.status in started and not self.started_on:
            self.started_on = nowdate()

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
        if self.initiation_date and self.due_date and getdate(self.initiation_date) > getdate(self.due_date):
            frappe.throw(_("Initiation Date cannot be after the Due Date."))

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
    the configured grace period. Original due date is preserved. (BRD FR-09, Sec-9)
    """
    settings = frappe.get_single("Compliance Settings")
    grace = int(getattr(settings, "overdue_grace_days", 0) or 0)
    cutoff = add_days(getdate(nowdate()), -grace)

    overdue_records = frappe.get_all(
        REQUEST_DOCTYPE,
        filters={
            "status": ["in", OPEN_STATUSES],
            "due_date": ["<", cutoff],
            "is_active": 1,
        },
        pluck="name",
    )

    for name in overdue_records:
        frappe.db.set_value(REQUEST_DOCTYPE, name, "status", "Overdue", update_modified=False)
        frappe.logger("compliance_overdue").info(f"{name} → Overdue (due_date < {cutoff})")

    if overdue_records:
        frappe.db.commit()

    return len(overdue_records)


# ======================= Alert / Email scheduler (BRD FR-08, Sec-11) =======================

def send_compliance_alerts():
    """
    Daily job: send email/in-app notifications for upcoming due dates per risk-tier alert
    day configuration in Compliance Settings. (BRD FR-08, FR-09, Sec-11)
    """
    settings = frappe.get_single("Compliance Settings")
    today = getdate(nowdate())

    tier_config = {
        "Critical": {
            "alert_days_field": "critical_alert_days",
            "notify_responsible": getattr(settings, "critical_notify_responsible", 1),
            "notify_dept_head": getattr(settings, "critical_notify_dept_head", 1),
            "notify_unit_head": getattr(settings, "critical_notify_unit_head", 1),
            "notify_reviewer": getattr(settings, "critical_notify_reviewer", 0),
            "notify_ceo": getattr(settings, "critical_notify_ceo", 1),
            "notify_role": getattr(settings, "critical_notify_role", None),
            "urgent_threshold": 7,
        },
        "High": {
            "alert_days_field": "high_alert_days",
            "notify_responsible": getattr(settings, "high_notify_responsible", 1),
            "notify_dept_head": getattr(settings, "high_notify_dept_head", 1),
            "notify_unit_head": getattr(settings, "high_notify_unit_head", 1),
            "notify_reviewer": getattr(settings, "high_notify_reviewer", 0),
            "notify_ceo": getattr(settings, "high_notify_ceo", 0),
            "notify_role": getattr(settings, "high_notify_role", None),
            "urgent_threshold": 7,
        },
        "Medium": {
            "alert_days_field": "medium_alert_days",
            "notify_responsible": getattr(settings, "medium_notify_responsible", 1),
            "notify_dept_head": getattr(settings, "medium_notify_dept_head", 1),
            "notify_unit_head": getattr(settings, "medium_notify_unit_head", 0),
            "notify_reviewer": getattr(settings, "medium_notify_reviewer", 0),
            "notify_ceo": getattr(settings, "medium_notify_ceo", 0),
            "notify_role": getattr(settings, "medium_notify_role", None),
            "urgent_threshold": 7,
        },
        "Low": {
            "alert_days_field": "low_alert_days",
            "notify_responsible": getattr(settings, "low_notify_responsible", 1),
            "notify_dept_head": getattr(settings, "low_notify_dept_head", 1),
            "notify_unit_head": getattr(settings, "low_notify_unit_head", 0),
            "notify_reviewer": getattr(settings, "low_notify_reviewer", 0),
            "notify_ceo": getattr(settings, "low_notify_ceo", 0),
            "notify_role": getattr(settings, "low_notify_role", None),
            "urgent_threshold": 7,
        },
    }

    alert_count = 0

    for tier, cfg in tier_config.items():
        # Get configured alert days for this tier
        alert_days_rows = getattr(settings, cfg["alert_days_field"], []) or []
        alert_day_values = []
        for row in alert_days_rows:
            days_val = frappe.db.get_value("Alert Day", row.alert_day, "days")
            if days_val is not None:
                alert_day_values.append(int(days_val))

        if not alert_day_values:
            continue

        for days_before in alert_day_values:
            target_date = add_days(today, days_before)
            is_urgent = days_before <= cfg["urgent_threshold"]

            records = frappe.get_all(
                REQUEST_DOCTYPE,
                filters={
                    "risk_tier": tier,
                    "due_date": target_date,
                    "status": ["in", OPEN_STATUSES],
                    "is_active": 1,
                },
                fields=[
                    "name", "compliance", "responsible_person", "backup_owner",
                    "reviewer", "department_head", "unit_head", "due_date",
                    "risk_tier", "status",
                ],
            )

            for rec in records:
                recipients = _build_recipients(rec, cfg, settings)
                if recipients:
                    _send_alert_email(rec, recipients, days_before, is_urgent)
                    alert_count += 1

    return alert_count


def _build_recipients(rec, cfg, settings):
    """Build a deduplicated list of email recipients for an alert."""
    recipients = set()

    if cfg["notify_responsible"] and rec.get("responsible_person"):
        email = frappe.db.get_value("User", rec.responsible_person, "email")
        if email:
            recipients.add(email)

    if cfg["notify_dept_head"] and rec.get("department_head"):
        email = frappe.db.get_value("User", rec.department_head, "email")
        if email:
            recipients.add(email)

    if cfg["notify_unit_head"] and rec.get("unit_head"):
        email = frappe.db.get_value("User", rec.unit_head, "email")
        if email:
            recipients.add(email)

    if cfg["notify_reviewer"] and rec.get("reviewer"):
        email = frappe.db.get_value("User", rec.reviewer, "email")
        if email:
            recipients.add(email)

    if cfg["notify_ceo"]:
        # Notify all users with 'CEO' role (or use a fixed email from settings if added later)
        ceo_users = frappe.get_all(
            "Has Role",
            filters={"role": "CEO", "parenttype": "User"},
            pluck="parent",
        )
        for u in ceo_users:
            email = frappe.db.get_value("User", u, "email")
            if email:
                recipients.add(email)

    if cfg.get("notify_role"):
        role_users = frappe.get_all(
            "Has Role",
            filters={"role": cfg["notify_role"], "parenttype": "User"},
            pluck="parent",
        )
        for u in role_users:
            email = frappe.db.get_value("User", u, "email")
            if email:
                recipients.add(email)

    return list(recipients)


def _compliance_title(rec):
    return frappe.db.get_value("Compliance", rec.get("compliance"), "compliance") or rec.name


def _send_alert_email(rec, recipients, days_before, is_urgent):
    """Send a single alert email and log the delivery attempt. (BRD FR-08, Sec-11)"""
    subject_prefix = "⚠️ URGENT — " if is_urgent else ""
    subject = _(
        "{0}Compliance Alert: {1} due in {2} day(s) [{3}]"
    ).format(subject_prefix, _compliance_title(rec), days_before, rec.risk_tier)

    record_url = frappe.utils.get_url(f"/app/compliance-request/{rec.name}")
    message = _(
        """
        <p>This is a reminder that the following compliance obligation is due in <strong>{days}</strong> day(s).</p>
        <table style="border-collapse:collapse; width:100%;">
          <tr><td style="padding:4px 8px;"><strong>Record</strong></td><td><a href="{url}">{name}</a></td></tr>
          <tr><td style="padding:4px 8px;"><strong>Compliance</strong></td><td>{compliance_name}</td></tr>
          <tr><td style="padding:4px 8px;"><strong>Due Date</strong></td><td>{due_date}</td></tr>
          <tr><td style="padding:4px 8px;"><strong>Status</strong></td><td>{status}</td></tr>
          <tr><td style="padding:4px 8px;"><strong>Risk Tier</strong></td><td>{risk_tier}</td></tr>
        </table>
        <p>Please upload mandatory evidence and request closure before the due date.</p>
        """
    ).format(
        days=days_before,
        url=record_url,
        name=rec.name,
        compliance_name=_compliance_title(rec),
        due_date=rec.due_date,
        status=rec.status,
        risk_tier=rec.risk_tier,
    )

    try:
        frappe.sendmail(
            recipients=recipients,
            subject=subject,
            message=message,
            reference_doctype=REQUEST_DOCTYPE,
            reference_name=rec.name,
            now=True,
        )
        frappe.logger("compliance_alerts").info(
            f"Alert sent: {rec.name} | {days_before}d | to={recipients}"
        )
    except Exception as e:
        frappe.logger("compliance_alerts").error(
            f"Alert FAILED: {rec.name} | {days_before}d | error={e}"
        )
