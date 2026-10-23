# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, getdate, nowdate, now_datetime


MASTER_DOCTYPE = "Compliance"
LEAD_DAYS_FIELD = "days_to_start_in_advance"

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
        self.set_original_due_date()
        self.set_initiation_date()
        self.populate_evidence_rows()
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

    # ---------- dates ----------
    def set_original_due_date(self):
        if self.due_date and not self.original_due_date:
            self.original_due_date = self.due_date

    def set_initiation_date(self):
        if self.initiation_date or not self.due_date:
            return
        lead_days = frappe.db.get_value(
            MASTER_DOCTYPE, self.compliance_master, LEAD_DAYS_FIELD
        ) or 0
        self.initiation_date = add_days(getdate(self.due_date), -int(lead_days))

    # ---------- evidence rows ----------
    def populate_evidence_rows(self):
        if not self.is_new() or self.evidence_items:
            return
        master = frappe.get_doc(MASTER_DOCTYPE, self.compliance_master)
        for rule in master.evidence_rules:
            self.append("evidence_items", {
                "evidence_type": rule.evidence_type,
                "is_mandatory": rule.is_mandatory,
                "is_payment_proof": rule.is_payment_proof,
            })

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
            self.risk_tier == "Critical"
            and self.reviewer
            and self.reviewer == self.responsible_person
        ):
            self.block(_("For Critical records the Reviewer must be a different person from the Responsible Person."))

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

    # ---------- duplicates  ----------
    def validate_duplicate(self):
        if not (self.compliance_master and self.compliance_unit and self.due_date):
            return
        dup = frappe.db.exists(self.doctype, {
            "compliance_master": self.compliance_master,
            "compliance_unit": self.compliance_unit,
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

        recurrence = frappe.db.get_value(
            MASTER_DOCTYPE, self.compliance_master, "recurrence"
        )
        months = RECURRENCE_MONTHS.get(recurrence)
        if not months:
            return  # One-time compliance, no next cycle

        # Avoid duplicates
        if frappe.db.exists(self.doctype, {"previous_record": self.name}):
            return

        frappe.get_doc({
            "doctype": self.doctype,
            "compliance_master": self.compliance_master,
            "compliance_unit": self.compliance_unit,
            "responsible_person": self.responsible_person,
            "reviewer": self.reviewer,
            "department_head": self.department_head,
            "backup_owner": self.backup_owner,
            "due_date": add_months(getdate(self.due_date), months),
            "previous_record": self.name,
            "status": "Upcoming",
        }).insert(ignore_permissions=True)
