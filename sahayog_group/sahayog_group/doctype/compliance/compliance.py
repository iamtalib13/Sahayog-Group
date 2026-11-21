import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, getdate, nowdate


class Compliance(Document):
    def validate(self):
        self.compliance_name = (self.compliance_name or getattr(self, "compliance", None) or "").strip()
        if self.is_rent:
            self.category = "Rent & Lease"
            if not self.obligation_type:
                self.obligation_type = "Agreement"
        self.fill_department_head()
        self.validate_assignments()
        self.validate_duplicate()
        self.validate_maker_checker()
        self.validate_rent_details()
        from sahayog_group.sahayog_group.rent_landlord_validation import validate_landlords
        validate_landlords(self)


    def fill_department_head(self):
        """Department Head comes from the Compliance Department and is kept in Assignments."""
        if not self.department:
            return
        head = frappe.db.get_value("Compliance Department", self.department, "department_head")
        if not head:
            return
        self.department_head = head
        full_name = frappe.db.get_value("User", head, "full_name") or head
        for row in self.get("assignments") or []:
            if row.role == "Department Head":
                row.user = head
                row.name1 = full_name
                return
        self.append("assignments", {"role": "Department Head", "user": head, "name1": full_name})

    def get_assignment_user(self, role):
        for row in self.get("assignments") or []:
            if row.role == role:
                return row.user
        return None

    def validate_assignments(self):
        seen_roles = set()
        for idx, row in enumerate(self.get("assignments") or [], 1):
            if not row.role:
                frappe.throw(_("Row {0}: Role is required in Assignments.").format(idx), title=_("Assignments"))
            if not row.user:
                frappe.throw(_("Row {0}: User is required in Assignments.").format(idx), title=_("Assignments"))
            if row.role in seen_roles:
                frappe.throw(_("Role {0} is added more than once in Assignments.").format(frappe.bold(row.role)), title=_("Assignments"))
            seen_roles.add(row.role)

    def validate_duplicate(self):
        """Same Compliance Name is allowed for a different Department / Project / Company, not for the same combination."""
        filters = {"compliance_name": self.compliance_name, "name": ["!=", self.name or ""]}
        for f in ("department", "project", "compliance_company"):
            value = self.get(f)
            filters[f] = value if value else ["is", "not set"]
        dup = frappe.db.exists("Compliance", filters)
        if dup:
            frappe.throw(
                _("Compliance {0} already exists for this Department, Project and Company ({1}).").format(
                    frappe.bold(self.compliance_name), dup
                ),
                title=_("Duplicate Compliance"),
            )

    def validate_maker_checker(self):
        """Critical compliance: Reviewer must be a different person from the Responsible Person (BRD section 8)."""
        responsible = self.get_assignment_user("Responsible Person")
        reviewer = self.get_assignment_user("Reviewer")
        if self.risk_tier == "Critical" and reviewer and reviewer == responsible:
            frappe.throw(
                _("For Risk Tier Critical the Reviewer must be a different person from the Responsible Person."),
                title=_("Maker-Checker"),
            )



    def validate_rent_details(self):
        if not self.is_rent and self.category != "Rent & Lease":
            return
        
        landlords = self.get("landlords") or []
        if landlords:
            import re
            pan_pattern = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
            total_ratio = 0.0

            for idx, l in enumerate(landlords, 1):
                ratio = float(l.share_ratio or 0)
                if ratio < 0:
                    frappe.throw(
                        _("Row #{0}: Share Ratio cannot be negative.").format(idx),
                        title=_("Invalid Share Ratio")
                    )
                total_ratio += ratio

                if l.landlord_pan:
                    pan_upper = l.landlord_pan.strip().upper()
                    l.landlord_pan = pan_upper
                    if not pan_pattern.match(pan_upper):
                        frappe.throw(
                            _("Row #{0}: Invalid Landlord PAN '{1}'. PAN format must be 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F).").format(idx, pan_upper),
                            title=_("Invalid Landlord PAN")
                        )

            if round(total_ratio, 2) != 100.0:
                frappe.throw(
                    _("Total Landlord Share Ratio must be exactly 100%. Current total: {0}%").format(round(total_ratio, 2)),
                    title=_("Invalid Share Ratio")
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
    def get_role_user(role):
        if hasattr(compliance_doc, "get_assignment_user"):
            return compliance_doc.get_assignment_user(role)
        for row in compliance_doc.get("assignments") or []:
            if row.get("role") == role:
                return row.get("user")
        return None

    req = frappe.get_doc({
        "doctype": "Compliance Request",
        "compliance": compliance_doc.name,
        "category": compliance_doc.category,
        "project": compliance_doc.project,
        "department": compliance_doc.department,
        "company": compliance_doc.compliance_company,
        "risk_tier": compliance_doc.risk_tier,
        "responsible_person": get_role_user("Responsible Person"),
        "backup_owner": get_role_user("Backup Owner"),
        "reviewer": get_role_user("Reviewer"),
        "department_head": get_role_user("Department Head"),
        "unit_head": get_role_user("Unit Head"),
        "central_compliance_owner": get_role_user("Central Compliance Owner"),
        "due_date": due_date,
        "original_due_date": due_date,
        "status": "Upcoming",
        "previous_record": previous_record,
    })
    req.flags.ignore_permissions = True
    req.insert()
    return req


def check_and_create_all_compliance_requests():
    """Daily scheduler job: creates the next Request when today reaches (due-cycle start - days in advance)."""
    names = frappe.get_all("Compliance", filters={"is_active": 1, "start_date": ["is", "set"]}, pluck="name")
    for name in names:
        try:
            auto_create_compliance_requests_for_doc(frappe.get_doc("Compliance", name))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "Auto-create Compliance Request failed: %s" % name)


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
        return f"<span class='indicator-pill {color}'>{st}</span>"

    rows_html = []
    resp_user = doc.get_assignment_user("Responsible Person") or "-"

    if requests:
        for r in requests:
            start_src = r.initiation_date or doc.start_date
            start_d = frappe.format(start_src, {"fieldtype": "Date"}) if start_src else "-"
            due_d = frappe.format(r.due_date, {"fieldtype": "Date"}) if r.due_date else "-"
            closed_d = frappe.format(r.closed_on, {"fieldtype": "Date"}) if r.closed_on else "-"
            user_val = r.responsible_person or resp_user
            req_link = f"<a href='/desk/compliance-request/{r.name}' style='font-weight: 600;'>{r.name}</a>"
            badge = get_badge(r.status)

            rows_html.append(f"<tr><td>{req_link}</td><td>{start_d}</td><td>{due_d}</td><td>{user_val}</td><td>{closed_d}</td><td>{badge}</td></tr>")
    else:
        c1_start = getdate(doc.start_date) if doc.start_date else None
        c1_due = _calc_due_date(c1_start, doc.recurrence) if c1_start else None
        c1_start_str = frappe.format(c1_start, {"fieldtype": "Date"}) if c1_start else "-"
        c1_due_str = frappe.format(c1_due, {"fieldtype": "Date"}) if c1_due else "-"
        not_gen = "<span class='text-muted'>Not Generated Yet</span>"
        rows_html.append(f"<tr><td>{not_gen}</td><td>{c1_start_str}</td><td>{c1_due_str}</td><td>{resp_user}</td><td>-</td><td>{get_badge('Not Started')}</td></tr>")

    table_body = "\n".join(rows_html)
    return (
        "<div style='padding: 10px 0; overflow-x: auto; width: 100%;'>"
        "<table class='table table-bordered table-hover' style='width: 100%; min-width: 650px; margin-bottom: 0;'>"
        "<thead style='background-color: var(--table-header-bg, #f4f5f7);'>"
        "<tr>"
        "<th style='width: 22%;'>Request ID</th>"
        "<th style='width: 16%;'>Start Date</th>"
        "<th style='width: 16%;'>Due Date</th>"
        "<th style='width: 20%;'>Assigned To</th>"
        "<th style='width: 13%;'>Closed Date</th>"
        "<th style='width: 13%;'>Status</th>"
        "</tr>"
        "</thead>"
        "<tbody>"
        + table_body +
        "</tbody>"
        "</table>"
        "</div>"
    )

@frappe.whitelist()
def get_pending_requests_summary(compliance_names=None):
    """Return pending request counts and details for given compliance masters."""
    import json
    if isinstance(compliance_names, str):
        try:
            compliance_names = json.loads(compliance_names)
        except Exception:
            compliance_names = [compliance_names]

    if not compliance_names:
        return {}

    open_statuses = [
        "Draft", "Upcoming", "Action Required", "In Progress", "Application Submitted",
        "Awaiting Authority / Third Party", "Blocked / At Risk", "Completion Submitted", "Overdue"
    ]

    records = frappe.get_all(
        "Compliance Request",
        filters={
            "compliance": ["in", compliance_names],
            "status": ["in", open_statuses]
        },
        fields=["name", "compliance", "status", "due_date", "responsible_person", "reviewer"],
        order_by="due_date asc"
    )

    summary = {c: [] for c in compliance_names}
    for r in records:
        if r.compliance in summary:
            summary[r.compliance].append({
                "name": r.name,
                "status": r.status,
                "due_date": frappe.format(r.due_date, {"fieldtype": "Date"}) if r.due_date else "-",
                "responsible_person": r.responsible_person or "-",
                "reviewer": r.reviewer or "-"
            })

    return summary


@frappe.whitelist()
def get_user_open_compliance_count(user):
    """Get count of active assignments and open requests for a user."""
    if not user:
        return {"master_count": 0, "request_count": 0}
    master_count = frappe.db.count("Compliance Assignment Item", {"user": user})
    open_statuses = ["Draft", "Upcoming", "Action Required", "In Progress", "Application Submitted", "Awaiting Authority / Third Party", "Blocked / At Risk", "Completion Submitted", "Exception Requested", "Overdue"]
    req_count = frappe.db.count("Compliance Request", {
        "status": ["in", open_statuses],
        "responsible_person": user
    })
    return {"master_count": master_count, "request_count": req_count}


@frappe.whitelist()
def bulk_reassign_user_obligations(from_user, to_user, reason=None):
    """Bulk transfer all Compliance master assignments and open Requests from an exiting/inactive user to a new active user."""
    from frappe.utils import escape_html

    if not from_user or not to_user:
        frappe.throw(_("Both From User and To User are required."))
    if from_user == to_user:
        frappe.throw(_("From User and To User cannot be the same."))
    if not frappe.db.get_value("User", to_user, "enabled"):
        frappe.throw(_("Destination user {0} is not active.").format(to_user))

    to_user_name = frappe.db.get_value("User", to_user, "full_name") or to_user
    reason = (reason or "Employee exit / inactivation reassignment").strip()

    # 1. Update Compliance Assignment Item
    assignment_rows = frappe.get_all(
        "Compliance Assignment Item",
        filters={"user": from_user},
        fields=["name", "parent", "role"]
    )
    for row in assignment_rows:
        frappe.db.set_value(
            "Compliance Assignment Item",
            row.name,
            {"user": to_user, "name1": to_user_name},
            update_modified=False
        )

    # Also update department_head in Compliance if from_user was department_head
    for comp in frappe.get_all("Compliance", filters={"department_head": from_user}, pluck="name"):
        frappe.db.set_value("Compliance", comp, "department_head", to_user, update_modified=False)

    # 2. Update open Compliance Requests
    open_statuses = [
        "Draft", "Upcoming", "Action Required", "In Progress",
        "Application Submitted", "Awaiting Authority / Third Party",
        "Blocked / At Risk", "Completion Submitted", "Exception Requested", "Overdue"
    ]
    
    # Update responsible_person
    requests_resp = frappe.get_all(
        "Compliance Request",
        filters={"responsible_person": from_user, "status": ["in", open_statuses]},
        pluck="name"
    )
    for r_name in requests_resp:
        doc = frappe.get_doc("Compliance Request", r_name)
        doc.responsible_person = to_user
        doc.flags.ignore_permissions = True
        doc.save()
        doc.add_comment("Comment", f"Auto-reassigned from {from_user} to {to_user} on user exit. Reason: {escape_html(reason)}")

    # Update backup_owner
    requests_backup = frappe.get_all(
        "Compliance Request",
        filters={"backup_owner": from_user, "status": ["in", open_statuses]},
        pluck="name"
    )
    for r_name in requests_backup:
        frappe.db.set_value("Compliance Request", r_name, "backup_owner", to_user, update_modified=False)

    # Update reviewer
    requests_rev = frappe.get_all(
        "Compliance Request",
        filters={"reviewer": from_user, "status": ["in", open_statuses]},
        pluck="name"
    )
    for r_name in requests_rev:
        frappe.db.set_value("Compliance Request", r_name, "reviewer", to_user, update_modified=False)

    return {
        "reassigned_assignments": len(assignment_rows),
        "reassigned_requests": len(requests_resp),
    }

@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def cost_center_query(doctype, txt, searchfield, start, page_len, filters):
	from frappe.query_builder import DocType
	from frappe.query_builder.functions import Coalesce

	CostCenter = DocType("Cost Center")
	query = (
		frappe.qb.from_(CostCenter)
		.select(
			CostCenter.name,
			Coalesce(CostCenter.cost_center_name, "").as_("cost_center_name"),
		)
		.where(CostCenter.is_group == 0)
	)

	if txt:
		query = query.where(
			CostCenter.cost_center_name.like(f"%{txt}%")
			| CostCenter.cost_center_number.like(f"%{txt}%")
			| CostCenter.name.like(f"%{txt}%")
		)

	query = (
		query.orderby(CostCenter.cost_center_number)
		.orderby(CostCenter.cost_center_name)
		.offset(start)
		.limit(page_len)
	)

	return query.run(as_list=True)
