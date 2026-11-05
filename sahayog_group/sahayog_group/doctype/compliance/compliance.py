import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, getdate, nowdate


class Compliance(Document):
    def validate(self):
        self.compliance = (self.compliance or "").strip()
        self.validate_duplicate()
        self.validate_maker_checker()

    def validate_duplicate(self):
        """Same Compliance Name is allowed for a different Department / Project / Company, not for the same combination."""
        filters = {"compliance": self.compliance, "name": ["!=", self.name or ""]}
        for f in ("department", "project", "company"):
            value = self.get(f)
            filters[f] = value if value else ["is", "not set"]
        dup = frappe.db.exists("Compliance", filters)
        if dup:
            frappe.throw(
                _("Compliance {0} already exists for this Department, Project and Company ({1}).").format(
                    frappe.bold(self.compliance), dup
                ),
                title=_("Duplicate Compliance"),
            )

    def validate_maker_checker(self):
        """Critical compliance: Reviewer must be a different person from the Responsible Person (BRD section 8)."""
        if self.risk_tier == "Critical" and self.reviewer and self.reviewer == self.responsible_person:
            frappe.throw(
                _("For Risk Tier Critical the Reviewer must be a different person from the Responsible Person."),
                title=_("Maker-Checker"),
            )



def _calc_due_date(start_d, recurrence):
    if not start_d or not recurrence:
        return None
    r = recurrence.strip().lower()
    start_d = getdate(start_d)
    if r == "monthly":
        return add_months(start_d, 1)
    elif r == "quarterly":
        return add_months(start_d, 3)
    elif r == "half-yearly":
        return add_months(start_d, 6)
    elif r == "yearly":
        return add_months(start_d, 12)
    return start_d


def auto_create_compliance_requests_for_doc(doc):
    """
    Creates compliance requests based on start_date, recurrence, and days_to_start_in_advance.
    Cycle 1: start_date to due_date = start_date + recurrence.
    Cycle N: starts at Previous Due Date, due at start + recurrence.
    Auto-created when today >= (start_date - days_to_start_in_advance).
    """
    if not doc.start_date or not doc.is_active:
        return

    today = getdate(nowdate())
    adv_days = int(doc.days_to_start_in_advance or 0)

    # Check all existing requests sorted by due_date
    existing = frappe.get_all(
        "Compliance Request",
        filters={"compliance": doc.name},
        fields=["name", "initiation_date", "due_date"],
        order_by="due_date asc",
    )

    if not existing:
        # Cycle 1 check
        cycle1_start = getdate(doc.start_date)
        cycle1_due = _calc_due_date(cycle1_start, doc.recurrence)
        trigger_date = add_days(cycle1_start, -adv_days)

        if today >= trigger_date:
            create_request(doc, cycle1_start, cycle1_due)
    else:
        # Recurrent cycles
        if doc.recurrence and doc.recurrence != "One-time":
            last_req = existing[-1]
            last_due = getdate(last_req.due_date) if last_req.due_date else None
            if last_due:
                next_start = last_due
                next_due = _calc_due_date(next_start, doc.recurrence)
                trigger_date = add_days(next_start, -adv_days)

                # Check if already created for this next_due
                already_exists = any(
                    getdate(r.due_date) == next_due for r in existing if r.due_date
                )
                if not already_exists and today >= trigger_date:
                    create_request(doc, next_start, next_due, previous_record=last_req.name)


def create_request(compliance_doc, start_date, due_date, previous_record=None):
    req = frappe.get_doc({
        "doctype": "Compliance Request",
        "compliance": compliance_doc.name,
        "category": compliance_doc.category,
        "project": compliance_doc.project,
        "department": compliance_doc.department,
        "company": compliance_doc.company,
        "risk_tier": compliance_doc.risk_tier,
        "responsible_person": compliance_doc.responsible_person,
        "backup_owner": compliance_doc.backup_owner,
        "reviewer": compliance_doc.reviewer,
        "department_head": compliance_doc.department_head,
        "due_date": due_date,
        "original_due_date": due_date,
        "status": "Upcoming",
        "previous_record": previous_record,
    })
    req.flags.ignore_permissions = True
    req.insert()
    return req


def check_and_create_all_compliance_requests():
    """Daily scheduler job"""
    return  # Requests are created manually; automatic creation is switched off


@frappe.whitelist()
def get_requests_html(compliance_name=None):
    if not compliance_name or compliance_name in ["None", "undefined", "null"] or not frappe.db.exists("Compliance", compliance_name):
        return "<p class='text-muted' style='padding: 15px;'>Please save the Compliance first to view requests.</p>"

    doc = frappe.get_doc("Compliance", compliance_name)
    requests = frappe.get_all(
        "Compliance Request",
        filters={"compliance": compliance_name},
        fields=[
            "name",
            "initiation_date",
            "due_date",
            "responsible_person",
            "closed_on",
            "status",
        ],
        order_by="due_date asc, creation asc",
    )

    def get_badge(status):
        st = status or "Not Started"
        color_map = {
            "Not Started": "gray",
            "Draft": "gray",
            "Upcoming": "blue",
            "Action Required": "orange",
            "In Progress": "cyan",
            "Application Submitted": "yellow",
            "Awaiting Authority / Third Party": "yellow",
            "Blocked / At Risk": "purple",
            "Completion Submitted": "cyan",
            "Closed / Completed": "green",
            "Overdue": "red",
            "Exception Approved": "blue",
            "Superseded / Inactive": "gray",
        }
        color = color_map.get(st, "blue")
        return f'<span class="indicator-pill {color}">{st}</span>'

    rows_html = []

    if requests:
        for r in requests:
            start_src = r.initiation_date
            if not start_src and r.due_date:
                m = {"monthly": 1, "quarterly": 3, "half-yearly": 6, "yearly": 12}.get((doc.recurrence or "").strip().lower())
                start_src = add_months(getdate(r.due_date), -m) if m else r.due_date
            start_d = frappe.format(start_src, {"fieldtype": "Date"}) if start_src else "-"
            due_d = frappe.format(r.due_date, {"fieldtype": "Date"}) if r.due_date else "-"
            closed_d = frappe.format(r.closed_on, {"fieldtype": "Date"}) if r.closed_on else "-"
            user_val = r.responsible_person or doc.responsible_person or "-"
            req_link = f'<a href="/app/compliance-request/{r.name}" style="font-weight: 600;">{r.name}</a>'
            badge = get_badge(r.status)

            rows_html.append(f"""
                <tr>
                    <td>{req_link}</td>
                    <td>{start_d}</td>
                    <td>{due_d}</td>
                    <td>{user_val}</td>
                    <td>{closed_d}</td>
                    <td>{badge}</td>
                </tr>
            """)

    if not requests:
        c1_start = getdate(doc.start_date) if doc.start_date else None
        c1_due = _calc_due_date(c1_start, doc.recurrence) if c1_start else None
        c1_start_str = frappe.format(c1_start, {"fieldtype": "Date"}) if c1_start else "-"
        c1_due_str = frappe.format(c1_due, {"fieldtype": "Date"}) if c1_due else "-"
        rows_html.append(f"""
            <tr>
                <td><span class="text-muted">Not Generated Yet</span></td>
                <td>{c1_start_str}</td>
                <td>{c1_due_str}</td>
                <td>{doc.responsible_person or "-"}</td>
                <td>-</td>
                <td>{get_badge("Not Started")}</td>
            </tr>
        """)

    table_body = "\n".join(rows_html)
    return f"""
    <div style="padding: 10px 0; overflow-x: auto; width: 100%; -webkit-overflow-scrolling: touch;">
        <table class="table table-bordered table-hover" style="width: 100%; min-width: 650px; margin-bottom: 0; white-space: nowrap;">
            <thead style="background-color: var(--table-header-bg, #f4f5f7);">
                <tr>
                    <th style="width: 22%;">Request ID</th>
                    <th style="width: 16%;">Start Date</th>
                    <th style="width: 16%;">Due Date</th>
                    <th style="width: 20%;">Assigned To</th>
                    <th style="width: 13%;">Closed Date</th>
                    <th style="width: 13%;">Status</th>
                </tr>
            </thead>
            <tbody>
                {table_body}
            </tbody>
        </table>
    </div>
    """
