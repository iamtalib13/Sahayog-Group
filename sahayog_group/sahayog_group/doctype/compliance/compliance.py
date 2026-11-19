import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, add_months, getdate, nowdate


class Compliance(Document):
    def validate(self):
        self.compliance = (self.compliance or "").strip()
        self.fill_department_head()
        self.validate_assignments()
        self.validate_duplicate()
        self.validate_maker_checker()

    def fill_department_head(self):
        """Department Head comes from the Compliance Department and is kept in Assignments."""
        if not self.department:
            return
        head = frappe.db.get_value("Compliance Department", self.department, "department_head")
        if not head:
            return
        self.department_head = head
        for row in self.get("assignments") or []:
            if row.role == "Department Head":
                row.user = head
                return
        self.append("assignments", {"role": "Department Head", "user": head})

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
        responsible = self.get_assignment_user("Responsible Person")
        reviewer = self.get_assignment_user("Reviewer")
        if self.risk_tier == "Critical" and reviewer and reviewer == responsible:
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
        "company": compliance_doc.company,
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


MASTER_ROLES = ("System Manager", "Compliance Master Admin")
PRECREATE_MAX = 120


def _is_master(user=None):
    return bool(set(MASTER_ROLES) & set(frappe.get_roles(user or frappe.session.user)))


def _notify(users, subject, message, doc):
    """In-app notification (bell icon) plus an email to each person."""
    from frappe.utils import escape_html, get_url_to_form

    link = get_url_to_form("Compliance", doc.name)
    label = "{0} ({1})".format(doc.compliance, doc.name)
    body = "<p>{0}</p><p><a href='{1}'>{2}</a></p>".format(escape_html(message), link, escape_html(label))
    for user in dict.fromkeys(u for u in users if u):
        try:
            frappe.get_doc({
                "doctype": "Notification Log",
                "for_user": user,
                "from_user": frappe.session.user,
                "type": "Alert",
                "document_type": "Compliance",
                "document_name": doc.name,
                "subject": escape_html(subject),
                "email_content": body,
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Pre-create notification failed")
        email = frappe.db.get_value("User", user, "email")
        if email:
            try:
                frappe.sendmail(
                    recipients=[email], subject=subject, message=body,
                    reference_doctype="Compliance", reference_name=doc.name,
                )
            except Exception:
                frappe.log_error(frappe.get_traceback(), "Pre-create email failed")


def _approvers(doc):
    """The person who created the Compliance; if that person is not a Master, every Compliance Master Admin."""
    users = [doc.owner]
    if not _is_master(doc.owner):
        users += frappe.get_all("Has Role", filters={"role": "Compliance Master Admin", "parenttype": "User"}, pluck="parent")
    return users


def _responsible(doc):
    return doc.get_assignment_user("Responsible Person")


def _set_precreate(name, **values):
    frappe.db.set_value("Compliance", name, values, update_modified=False)


def _create_cycles(doc, count):
    """Create `count` more Requests after the ones that already exist. Nothing is duplicated."""
    recurring = bool(doc.recurrence and doc.recurrence != "One-time")
    existing = frappe.get_all(
        "Compliance Request",
        filters={"compliance": doc.name, "status": ["!=", "Superseded / Inactive"]},
        fields=["name", "due_date"],
        order_by="due_date asc",
    )
    existing = [r for r in existing if r.due_date]
    dues = {getdate(r.due_date): r.name for r in existing}
    if existing:
        if not recurring:
            return 0
        start, previous = getdate(existing[-1].due_date), existing[-1].name
    else:
        start, previous = getdate(doc.start_date), None

    created = 0
    try:
        for i in range(count):
            due = _calc_due_date(start, doc.recurrence)
            if due in dues:
                previous = dues[due]
            else:
                req = create_request(doc, start, due, previous_record=previous)
                dues[due] = req.name
                previous = req.name
                created += 1
            if not recurring:
                break
            start = due
    except Exception:
        frappe.db.rollback()
        raise
    return created


def _accept(doc, count, requested_by):
    created = _create_cycles(doc, count)
    _set_precreate(doc.name, precreate_status="Created", precreate_count=count)
    _notify(
        [requested_by, _responsible(doc)],
        "Records created for {0}".format(doc.compliance),
        "{0} record(s) have been created in advance for this compliance.".format(created),
        doc,
    )
    return {"state": "Created", "created": created, "message": _("{0} record(s) created.").format(created)}


@frappe.whitelist()
def precreate_ask(compliance, answer):
    """Asked from the Compliance Master / System Manager when a Compliance is saved for the first time."""
    doc = frappe.get_doc("Compliance", compliance)
    doc.check_permission("read")
    if not _is_master():
        frappe.throw(_("Only a Compliance Master or System Manager can answer this."), title=_("Pre-create"))

    if str(answer).strip().lower() != "yes":
        _set_precreate(compliance, precreate_status="Not Required")
        return {"state": "Not Required", "message": _("Records will be created automatically before their due date.")}

    responsible = _responsible(doc)
    if not responsible:
        frappe.throw(_("Add a Responsible Person in Assignments first."), title=_("Pre-create"))
    _set_precreate(compliance, precreate_status="Asked")
    _notify(
        [responsible],
        "Pre-create records for {0}?".format(doc.compliance),
        "Do you want to pre-create records in advance for this compliance? "
        "Open it and click 'Pre-create Records Request' to choose how many records you need.",
        doc,
    )
    return {"state": "Asked", "message": _("The Responsible Person has been notified.")}


@frappe.whitelist()
def precreate_send_request(compliance, count):
    """Responsible Person asks for N records. A Master / System Manager using the button creates them directly."""
    doc = frappe.get_doc("Compliance", compliance)
    doc.check_permission("read")
    user = frappe.session.user
    master = _is_master()
    if not master and user not in (_responsible(doc), doc.get_assignment_user("Backup Owner")):
        frappe.throw(_("Only the Responsible Person or a Compliance Master can do this."), title=_("Pre-create"))
    if not doc.is_active:
        frappe.throw(_("This Compliance is not active."), title=_("Pre-create"))
    if not doc.start_date:
        frappe.throw(_("Set the Start Date first."), title=_("Pre-create"))
    count = int(count or 0)
    if count < 1 or count > PRECREATE_MAX:
        frappe.throw(_("Enter a count between 1 and {0}.").format(PRECREATE_MAX), title=_("Pre-create"))

    _set_precreate(
        compliance, precreate_status="Requested", precreate_count=count,
        precreate_period=doc.recurrence, precreate_requested_by=user,
    )
    if master:
        return _accept(doc, count, user)

    _notify(
        _approvers(doc),
        "Pre-create request: {0}".format(doc.compliance),
        "{0} has requested {1} record(s) to be created in advance for this compliance. "
        "Open it to accept or reject the request.".format(frappe.utils.get_fullname(user), count),
        doc,
    )
    return {"state": "Requested", "message": _("Request sent")}


@frappe.whitelist()
def precreate_decide(compliance, decision):
    """Compliance Master / System Manager accepts or rejects the request."""
    doc = frappe.get_doc("Compliance", compliance)
    doc.check_permission("read")
    if not _is_master():
        frappe.throw(_("Only a Compliance Master or System Manager can accept or reject."), title=_("Pre-create"))
    if doc.precreate_status != "Requested":
        frappe.throw(_("There is no pending pre-create request."), title=_("Pre-create"))

    requested_by = doc.precreate_requested_by
    if str(decision).strip().lower() == "accept":
        return _accept(doc, int(doc.precreate_count or 0), requested_by)

    _set_precreate(compliance, precreate_status="Rejected")
    _notify(
        [requested_by, _responsible(doc)],
        "Pre-create request rejected: {0}".format(doc.compliance),
        "Your request to pre-create records for this compliance has been rejected.",
        doc,
    )
    return {"state": "Rejected", "message": _("Request rejected.")}


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
            resp_user = doc.get_assignment_user("Responsible Person") if hasattr(doc, "get_assignment_user") else None
            user_val = r.responsible_person or resp_user or "-"
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
        resp_user = doc.get_assignment_user("Responsible Person") if hasattr(doc, "get_assignment_user") else "-"
        rows_html.append(f"""
            <tr>
                <td><span class="text-muted">Not Generated Yet</span></td>
                <td>{c1_start_str}</td>
                <td>{c1_due_str}</td>
                <td>{resp_user or "-"}</td>
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
