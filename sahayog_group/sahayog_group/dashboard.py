"""Role-wise dashboard for the Home tab of Compliance (BRD section 12).

Every number is read through frappe.get_list, so a user only ever sees the records that
the permission rules (permissions.py) allow. The view decides which widgets are shown.
"""

import frappe
from frappe import _
from frappe.utils import cint, date_diff, getdate, nowdate, now_datetime, strip_html, add_days

REQ = "Compliance Request"
CLOSED = "Closed / Completed"
SUBMITTED = "Completion Submitted"
OPEN = [
    "Draft", "Upcoming", "Action Required", "In Progress", "Application Submitted",
    "Awaiting Authority / Third Party", "Blocked / At Risk", SUBMITTED, "Overdue",
]
EXTERNAL = ("Application Submitted", "Awaiting Authority / Third Party")
TIER_WEIGHT = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
TIER_TONE = {"Critical": "red", "High": "amber", "Medium": "blue", "Low": "grey"}

FIELDS = [
    "name", "compliance", "status", "due_date", "risk_tier", "department", "project", "company",
    "responsible_person", "backup_owner", "reviewer", "unit_head", "department_head",
    "central_compliance_owner", "start_date", "initiation_date", "closed_on", "reviewer_decision",
    "rejection_reason", "reason_for_delay", "blocker", "next_action", "next_follow_up_date",
    "application_reference_no",
]

# key, label, roles that unlock the view
VIEWS = [
    ("master_admin", "Master Administrator", {"Compliance Master Admin"}),
    ("leadership", "Chairman / Promoter / CEO", {"Compliance Chairman", "Compliance Executive"}),
    ("chairman_office", "Chairman's Office / CCC / Audit", {"Compliance Viewer", "Compliance Auditor"}),
    ("central", "Central Compliance / Operations", {"Compliance Coordinator", "Compliance Operations Head"}),
    ("unit_head", "Unit Head", {"Compliance Facility Head"}),
    ("dept_head", "Department Head", {"Compliance Department Head"}),
    ("project_head", "Project Head", {"Compliance Project Head"}),
    ("responsible", "My Work", {"Compliance User", "Compliance Checker"}),
]


# ------------------------------------------------------------------ small helpers
def _link(text, name, dt=REQ):
    return {"text": text, "link": [dt, name]}


def _kpi(label, value, tone="blue", filters=None, hint=None):
    return {"label": label, "value": value, "tone": tone, "filters": filters, "hint": hint}


def _table(title, columns, rows, empty="Nothing to show."):
    return {"type": "table", "title": title, "columns": columns, "rows": rows, "empty": empty}


def _pct(a, b):
    return round(100.0 * a / b) if b else 0


def _days_text(days):
    if days is None:
        return "-"
    if days < 0:
        return "Overdue {0}d".format(-days)
    if days == 0:
        return "Today"
    return "in {0}d".format(days)


def _fmt(d):
    return frappe.utils.formatdate(d) if d else "-"


def _available_views(user):
    roles = set(frappe.get_roles(user))
    if user == "Administrator" or "System Manager" in roles:
        return list(VIEWS)
    return [v for v in VIEWS if roles & v[2]]


# ------------------------------------------------------------------ data context
class Ctx:
    def __init__(self, user):
        self.user = user
        self.today = getdate(nowdate())
        rows = frappe.get_list(
            REQ, fields=FIELDS, filters={"is_active": 1}, order_by="due_date asc", limit_page_length=100000
        )
        names = {r.compliance for r in rows if r.compliance}
        self.titles = {}
        self.compliance_days = {}
        if names:
            for c in frappe.get_all(
                "Compliance", filters={"name": ["in", list(names)]},
                fields=["name", "compliance_name", "days_to_start_in_advance"], limit_page_length=100000,
            ):
                self.titles[c.name] = c.compliance_name
                self.compliance_days[c.name] = cint(c.days_to_start_in_advance)

        self.rows = []
        for r in rows:
            if r.status in ("Superseded / Inactive", "Not Yet Applicable", "Exception Approved"):
                continue
            r.title = self.titles.get(r.compliance) or r.name
            r.days = date_diff(r.due_date, self.today) if r.due_date else None
            r.is_open = r.status in OPEN
            r.is_overdue = r.is_open and (r.status == "Overdue" or (r.days is not None and r.days < 0))
            self.rows.append(r)

        open_names = [r.name for r in self.rows if r.is_open]
        self.incomplete = set()
        if open_names:
            for e in frappe.get_all(
                "Evidence Item",
                filters={"parenttype": REQ, "parent": ["in", open_names], "is_mandatory": 1},
                fields=["parent", "file", "document_date"], limit_page_length=100000,
            ):
                if not e.file or not e.document_date:
                    self.incomplete.add(e.parent)
        self._alerts = None

    # alert rows (scoped by permission rules)
    @property
    def alerts(self):
        if self._alerts is None:
            self._alerts = frappe.get_list(
                "Alert Log",
                fields=["name", "compliance_request", "recipient", "alert_type", "sent_on",
                        "acknowledged", "acknowledged_on", "escalated", "escalated_on"],
                order_by="sent_on desc", limit_page_length=100000,
            )
        return self._alerts

    def title(self, name):
        for r in self.rows:
            if r.name == name:
                return r.title
        comp = frappe.db.get_value(REQ, name, "compliance")
        return (frappe.db.get_value("Compliance", comp, "compliance_name") if comp else None) or name

    def open(self):
        return [r for r in self.rows if r.is_open]

    def overdue(self):
        return [r for r in self.rows if r.is_overdue]

    def due_within(self, n):
        return [r for r in self.rows if r.is_open and not r.is_overdue and r.days is not None and 0 <= r.days <= n]

    def item_rows(self, rows, limit=15, extra=None):
        out = []
        for r in rows[:limit]:
            cells = [
                _link(r.title, r.name), r.status, _fmt(r.due_date), _days_text(r.days),
                {"text": r.risk_tier or "-", "tone": TIER_TONE.get(r.risk_tier, "grey")},
                r.responsible_person or "Unassigned",
            ]
            if extra:
                cells += [x(r) for x in extra]
            out.append(cells)
        return out


ITEM_COLS = ["Compliance", "Status", "Due Date", "Due", "Risk", "Owner"]


def _stats(c, rows=None):
    rows = c.rows if rows is None else rows
    closed = [r for r in rows if r.status == CLOSED]
    due_base = [r for r in rows if r.status == CLOSED or (r.days is not None and r.days <= 0 and r.is_open)]
    return {
        "total": len(rows),
        "open": len([r for r in rows if r.is_open]),
        "closed": len(closed),
        "overdue": len([r for r in rows if r.is_overdue]),
        "critical_overdue": len([r for r in rows if r.is_overdue and r.risk_tier == "Critical"]),
        "rate": _pct(len(closed), len(due_base)),
    }


def _group(c, title, key, label, rows=None, limit=15):
    rows = c.rows if rows is None else rows
    groups = {}
    for r in rows:
        groups.setdefault(r.get(key) or "Unassigned", []).append(r)
    out = []
    for name, rs in groups.items():
        s = _stats(c, rs)
        out.append([name, s["total"], s["open"], s["overdue"], s["closed"], "{0}%".format(s["rate"])])
    out.sort(key=lambda x: (-x[3], -x[2], x[0]))
    return _table(title, [label, "Total", "Open", "Overdue", "Closed", "Completion"], out[:limit])


def _scorecard(c, title, key="responsible_person", limit=15):
    """Indicative KPI score (BRD section 13). Weights are re-balanced over the parts that have data."""
    wins = {m.name: cint(m.acknowledgement_window_days) or 2 for m in frappe.get_all(
        "Compliance", fields=["name", "acknowledgement_window_days"], limit_page_length=100000)}
    req_comp = {r.name: r.compliance for r in c.rows}
    by_person = {}
    for r in c.rows:
        if r.get(key):
            by_person.setdefault(r.get(key), []).append(r)
    out = []
    for person, rs in by_person.items():
        parts = []
        # 30% on-time verified completion
        base = [r for r in rs if r.status == CLOSED or (r.days is not None and r.days <= 0 and r.is_open)]
        ontime = [r for r in rs if r.status == CLOSED and r.closed_on and getdate(r.closed_on) <= getdate(r.due_date)]
        if base:
            parts.append((30, _pct(len(ontime), len(base))))
        # 20% timely initiation
        pool = [r for r in rs if r.initiation_date or r.start_date or r.is_overdue]
        if pool:
            good = [r for r in pool if (r.initiation_date or r.start_date) and
                    getdate(r.initiation_date or r.start_date) <= getdate(r.due_date)]
            parts.append((20, _pct(len(good), len(pool))))
        # 20% overdue / critical risk management (severity weighted)
        if base:
            exp = sum(TIER_WEIGHT.get(r.risk_tier, 2) for r in rs if r.is_overdue)
            tot = sum(TIER_WEIGHT.get(r.risk_tier, 2) for r in base)
            parts.append((20, max(0, 100 - _pct(exp, tot))))
        # 15% evidence and record quality
        sub = [r for r in rs if r.status in (SUBMITTED, CLOSED) or r.rejection_reason]
        if sub:
            parts.append((15, 100 - _pct(len([r for r in sub if r.rejection_reason]), len(sub))))
        # 10% alert responsiveness
        al = [a for a in c.alerts if a.recipient == person]
        if al:
            ok = [a for a in al if a.acknowledged and a.acknowledged_on and
                  date_diff(a.acknowledged_on, a.sent_on) <= wins.get(req_comp.get(a.compliance_request), 2)]
            parts.append((10, _pct(len(ok), len(al))))
        wsum = sum(w for w, _s in parts)
        score = round(sum(w * s for w, s in parts) / wsum) if wsum else None
        s = _stats(c, rs)
        out.append([person, s["total"], s["overdue"], s["closed"], "-" if score is None else score])
    out.sort(key=lambda x: (-(x[4] if isinstance(x[4], int) else -1), x[0]))
    return _table(title + " (indicative score, weights to be calibrated after pilot)",
                  ["Person", "Assigned", "Overdue", "Closed", "KPI Score"], out[:limit])


def _ageing_overdue(c):
    buckets = [("1-7 days", 1, 7), ("8-30 days", 8, 30), ("31-60 days", 31, 60), ("60+ days", 61, 99999)]
    items = []
    for label, lo, hi in buckets:
        n = len([r for r in c.overdue() if r.days is not None and lo <= -r.days <= hi])
        items.append({"label": label, "value": n})
    return {"type": "bars", "title": "Overdue ageing", "items": items}


def _escalations(c, limit=15, only_open=True):
    rows = [a for a in c.alerts if a.alert_type == "Escalation" and (not only_open or not a.acknowledged)]
    out = []
    for a in rows[:limit]:
        age = date_diff(c.today, getdate(a.sent_on)) if a.sent_on else 0
        out.append([_link(c.title(a.compliance_request), a.compliance_request), a.recipient, _fmt(getdate(a.sent_on)),
                    "{0}d".format(age)])
    return rows, _table("Unresolved escalations", ["Compliance", "Escalated To", "Sent", "Age"], out,
                        "No unresolved escalations.")


def _esc_ageing(c):
    rows = [a for a in c.alerts if a.alert_type == "Escalation" and not a.acknowledged]
    b = [("0-2 days", 0, 2), ("3-7 days", 3, 7), ("8-14 days", 8, 14), ("15+ days", 15, 99999)]
    items = []
    for label, lo, hi in b:
        n = len([a for a in rows if a.sent_on and lo <= date_diff(c.today, getdate(a.sent_on)) <= hi])
        items.append({"label": label, "value": n})
    return {"type": "bars", "title": "Escalation ageing (unacknowledged)", "items": items}


def _recent_versions(doctypes, limit=12):
    rows = frappe.get_all(
        "Version", filters={"ref_doctype": ["in", doctypes]},
        fields=["ref_doctype", "docname", "owner", "creation"], order_by="creation desc", limit_page_length=limit,
    )
    return [[r.ref_doctype, r.docname, r.owner, frappe.utils.format_datetime(r.creation)] for r in rows]


def _action_log(limit=12):
    rows = frappe.get_all(
        "Comment", filters={"reference_doctype": REQ, "comment_type": "Comment"},
        fields=["reference_name", "owner", "content", "creation"], order_by="creation desc", limit_page_length=limit,
    )
    return [[_link(r.reference_name, r.reference_name), r.owner, (strip_html(r.content or ""))[:90],
             frappe.utils.format_datetime(r.creation)] for r in rows]


# ------------------------------------------------------------------ views
def _v_leadership(c):
    s = _stats(c)
    hi = [r for r in c.open() if r.risk_tier in ("Critical", "High") and (r.is_overdue or r.status == "Blocked / At Risk")]
    esc_rows = [a for a in c.alerts if a.alert_type == "Escalation" and not a.acknowledged]
    kpis = [
        _kpi("Completion rate", "{0}%".format(s["rate"]), "green" if s["rate"] >= 80 else "amber"),
        _kpi("Open", s["open"], "blue", {"status": ["in", OPEN]}),
        _kpi("Overdue", s["overdue"], "red" if s["overdue"] else "green", {"status": "Overdue"}),
        _kpi("Critical overdue", s["critical_overdue"], "red" if s["critical_overdue"] else "green",
             {"status": "Overdue", "risk_tier": "Critical"}),
        _kpi("Due in 7 days", len(c.due_within(7)), "amber"),
        _kpi("Due in 30 days", len(c.due_within(30)), "blue"),
        _kpi("Due in 60 days", len(c.due_within(60)), "blue"),
        _kpi("Due in 90 days", len(c.due_within(90)), "blue"),
        _kpi("High-risk exceptions", len(hi), "red" if hi else "green", None, "Critical/High that are overdue or blocked"),
        _kpi("Open escalations", len(esc_rows), "red" if esc_rows else "green"),
    ]
    crit = [r for r in c.overdue() if r.risk_tier in ("Critical", "High")]
    return [
        {"type": "kpis", "items": kpis},
        _table("Critical / High overdue items", ITEM_COLS, c.item_rows(crit), "No critical or high overdue items."),
        _group(c, "Hospital comparison", "company", "Hospital / Company"),
        _group(c, "Project launch risks", "project", "Project"),
        _esc_ageing(c),
        _group(c, "Department performance", "department", "Department"),
        _scorecard(c, "Person performance"),
    ]


def _v_chairman_office(c):
    s = _stats(c)
    esc_rows, esc_table = _escalations(c)
    review = [r for r in c.rows if r.status == SUBMITTED]
    kpis = [
        _kpi("Open", s["open"], "blue", {"status": ["in", OPEN]}),
        _kpi("Overdue", s["overdue"], "red" if s["overdue"] else "green", {"status": "Overdue"}),
        _kpi("Unresolved escalations", len(esc_rows), "red" if esc_rows else "green"),
        _kpi("Evidence pending review", len(review), "amber", {"status": SUBMITTED}),
        _kpi("Completion rate", "{0}%".format(s["rate"]), "green" if s["rate"] >= 80 else "amber"),
    ]
    return [
        {"type": "kpis", "items": kpis},
        _ageing_overdue(c),
        esc_table,
        _table("Overdue register", ITEM_COLS, c.item_rows(c.overdue(), 20), "No overdue items."),
        _table("Action log (latest)", ["Record", "By", "Action", "When"], _action_log(), "No actions yet."),
        _table("Audit history (latest changes)", ["DocType", "Record", "By", "When"],
               _recent_versions([REQ, "Compliance"]), "No changes recorded."),
    ]


def _v_central(c):
    s = _stats(c)
    unassigned = [r for r in c.open() if not r.responsible_person]
    incomplete = [r for r in c.open() if r.name in c.incomplete]
    ext = [r for r in c.rows if r.status in EXTERNAL]
    upcoming = [r for r in c.rows if r.is_open and not r.is_overdue and r.days is not None and 0 <= r.days <= 30]
    esc_rows, esc_table = _escalations(c)
    kpis = [
        _kpi("Open", s["open"], "blue", {"status": ["in", OPEN]}),
        _kpi("Overdue", s["overdue"], "red" if s["overdue"] else "green", {"status": "Overdue"}),
        _kpi("Renewals due in 30 days", len(upcoming), "amber"),
        _kpi("Unassigned records", len(unassigned), "red" if unassigned else "green"),
        _kpi("Incomplete evidence", len(incomplete), "amber"),
        _kpi("Authority pending", len(ext), "blue"),
        _kpi("Escalation queue", len(esc_rows), "red" if esc_rows else "green"),
    ]
    rec = {}
    for m in frappe.get_list("Compliance", fields=["recurrence"], limit_page_length=100000):
        rec[m.recurrence or "Not set"] = rec.get(m.recurrence or "Not set", 0) + 1
    return [
        {"type": "kpis", "items": kpis},
        _table("Upcoming renewals (30 days)", ITEM_COLS, c.item_rows(upcoming), "No renewals due in 30 days."),
        _table("Unassigned records", ITEM_COLS, c.item_rows(unassigned), "Every open record has an owner."),
        _table("Incomplete evidence", ITEM_COLS, c.item_rows(incomplete), "No open record is missing mandatory evidence."),
        _table("External authority pending", ["Compliance", "Status", "Reference No", "Next Follow-up", "Owner"],
               [[_link(r.title, r.name), r.status, r.application_reference_no or "-", _fmt(r.next_follow_up_date),
                 r.responsible_person or "Unassigned"] for r in ext[:15]], "No cases pending with an authority."),
        _group(c, "Owner workload", "responsible_person", "Owner"),
        esc_table,
        {"type": "bars", "title": "Recurring obligations", "items": [{"label": k, "value": v} for k, v in sorted(rec.items())]},
    ]


def _v_unit_head(c):
    s = _stats(c)
    risky = [r for r in c.open() if r.is_overdue or r.status == "Blocked / At Risk"]
    review = [r for r in c.rows if r.status == SUBMITTED]
    kpis = [
        _kpi("Records", s["total"], "blue"),
        _kpi("Completion rate", "{0}%".format(s["rate"]), "green" if s["rate"] >= 80 else "amber"),
        _kpi("Overdue", s["overdue"], "red" if s["overdue"] else "green", {"status": "Overdue"}),
        _kpi("At risk / blocked", len([r for r in c.rows if r.status == "Blocked / At Risk"]), "amber",
             {"status": "Blocked / At Risk"}),
        _kpi("Due in 7 days", len(c.due_within(7)), "amber"),
        _kpi("Due in 30 days", len(c.due_within(30)), "blue"),
        _kpi("Awaiting review", len(review), "amber", {"status": SUBMITTED}),
    ]
    return [
        {"type": "kpis", "items": kpis},
        _group(c, "Department-wise compliance", "department", "Department"),
        _table("Overdue / at-risk items", ITEM_COLS, c.item_rows(risky), "Nothing overdue or at risk."),
        _table("Upcoming deadlines (30 days)", ITEM_COLS, c.item_rows(c.due_within(30)), "No deadlines in 30 days."),
        _table("Evidence awaiting review", ITEM_COLS, c.item_rows(review), "Nothing waiting for review."),
        _group(c, "Staff ownership", "responsible_person", "Owner"),
        _scorecard(c, "KPI scorecard"),
    ]


def _v_dept_head(c):
    s = _stats(c)
    pending_up = [r for r in c.open() if r.name in c.incomplete]
    await_act = [r for r in c.rows if r.status in ("Upcoming", "Action Required", "Blocked / At Risk", SUBMITTED)]
    delays = [r for r in c.open() if r.is_overdue or r.status == "Blocked / At Risk"]

    def internal(r):
        d = c.compliance_days.get(r.compliance, 0)
        return _fmt(add_days(r.due_date, -d)) if r.due_date else "-"

    kpis = [
        _kpi("Obligations", s["total"], "blue"),
        _kpi("Due in 7 days", len(c.due_within(7)), "amber"),
        _kpi("Due in 30 days", len(c.due_within(30)), "blue"),
        _kpi("Overdue", s["overdue"], "red" if s["overdue"] else "green", {"status": "Overdue"}),
        _kpi("Pending uploads", len(pending_up), "amber"),
        _kpi("Awaiting action / review", len(await_act), "amber"),
        _kpi("Delays", len(delays), "red" if delays else "green"),
    ]
    return [
        {"type": "kpis", "items": kpis},
        _table("Department obligations", ["Compliance", "Owner", "Internal Start", "Statutory Due", "Status"],
               [[_link(r.title, r.name), r.responsible_person or "Unassigned", internal(r), _fmt(r.due_date), r.status]
                for r in c.open()[:20]], "No open obligations."),
        _table("Pending uploads (mandatory evidence missing)", ITEM_COLS, c.item_rows(pending_up),
               "No pending uploads."),
        _table("Tasks awaiting action / review", ITEM_COLS, c.item_rows(await_act), "Nothing waiting."),
        _table("Delays and corrective actions", ["Compliance", "Status", "Due", "Blocker / Reason", "Next Action"],
               [[_link(r.title, r.name), r.status, _days_text(r.days), r.blocker or r.reason_for_delay or "-",
                 r.next_action or "-"] for r in delays[:15]], "No delays."),
        _group(c, "Owner workload", "responsible_person", "Owner"),
    ]


def _v_responsible(c):
    me = c.user
    mine = [r for r in c.rows if me in (r.responsible_person, r.backup_owner)]
    open_mine = [r for r in mine if r.is_open]
    review = [r for r in c.rows if r.reviewer == me and r.status == SUBMITTED]
    evidence = [r for r in open_mine if r.name in c.incomplete]
    rejected = [r for r in open_mine if r.reviewer_decision == "Rejected" and r.status == "In Progress"]
    overdue = [r for r in open_mine if r.is_overdue]
    pending_alerts = [a for a in c.alerts if a.recipient == me and not a.acknowledged]
    kpis = [
        _kpi("My open tasks", len(open_mine), "blue"),
        _kpi("Next 7 days", len([r for r in open_mine if r.days is not None and 0 <= r.days <= 7]), "amber"),
        _kpi("Next 30 days", len([r for r in open_mine if r.days is not None and 0 <= r.days <= 30]), "blue"),
        _kpi("Overdue", len(overdue), "red" if overdue else "green", {"status": "Overdue", "responsible_person": me}),
        _kpi("Evidence required", len(evidence), "amber"),
        _kpi("Rejected", len(rejected), "red" if rejected else "green"),
        _kpi("Alerts to acknowledge", len(pending_alerts), "red" if pending_alerts else "green"),
        _kpi("Awaiting my review", len(review), "amber"),
    ]
    return [
        {"type": "kpis", "items": kpis},
        _table("My tasks", ITEM_COLS[:5] + ["Next Action"],
               [row[:5] + [r.next_action or "-"] for row, r in zip(c.item_rows(open_mine, 20), open_mine[:20])],
               "You have no open tasks."),
        _table("Overdue actions", ITEM_COLS, c.item_rows(overdue), "Nothing overdue."),
        _table("Evidence required", ITEM_COLS, c.item_rows(evidence), "All mandatory evidence is uploaded."),
        _table("Rejected - needs correction", ["Compliance", "Rejection Reason", "Due"],
               [[_link(r.title, r.name), r.rejection_reason or "-", _days_text(r.days)] for r in rejected[:15]],
               "No rejected submissions."),
        _table("Alerts awaiting acknowledgement", ["Compliance", "Alert", "Sent"],
               [[_link(c.title(a.compliance_request), a.compliance_request), a.alert_type,
                 frappe.utils.format_datetime(a.sent_on)] for a in pending_alerts[:15]], "No alerts waiting."),
        _table("Awaiting my review", ITEM_COLS, c.item_rows(review), "Nothing waiting for your review."),
    ]


def _v_project_head(c):
    user = c.user
    admin = user == "Administrator" or "System Manager" in frappe.get_roles(user) or "Compliance Master Admin" in frappe.get_roles(user)
    filters = {} if admin else {"project_head": user}
    projects = frappe.get_all(
        "Compliance Project", filters=filters,
        fields=["name", "go_live_date", "planned_opening_date", "go_live_status", "project_head"], limit_page_length=1000,
    )
    names = {p.name for p in projects}
    rows = [r for r in c.rows if r.project in names]
    out, risky = [], 0
    for p in projects:
        pr = [r for r in rows if r.project == p.name]
        closed = [r for r in pr if r.status == CLOSED]
        open_ = [r for r in pr if r.is_open]
        over = [r for r in open_ if r.is_overdue]
        crit = [r for r in open_ if r.risk_tier == "Critical"]
        target = p.go_live_date or p.planned_opening_date
        late = [r for r in open_ if target and r.due_date and getdate(r.due_date) > getdate(target)]
        at_risk = bool(over or late)
        risky += 1 if at_risk else 0
        out.append([
            p.name, p.go_live_status or "-", _fmt(target), len(closed), len(open_), len(over), len(crit),
            "{0}%".format(_pct(len(closed), len(pr))),
            {"text": "At risk" if at_risk else "On track", "tone": "red" if at_risk else "green"},
        ])
    kpis = [
        _kpi("Projects", len(projects), "blue"),
        _kpi("Approvals received", len([r for r in rows if r.status == CLOSED]), "green"),
        _kpi("Approvals pending", len([r for r in rows if r.is_open]), "amber"),
        _kpi("Overdue approvals", len([r for r in rows if r.is_overdue]), "red"),
        _kpi("Projects at risk", risky, "red" if risky else "green"),
    ]
    return [
        {"type": "kpis", "items": kpis},
        _table("Project readiness", ["Project", "Go-live Status", "Target Date", "Received", "Pending", "Overdue",
                                      "Critical Open", "Readiness", "Launch Impact"], out, "No projects in your scope."),
        _table("Approval checklist", ITEM_COLS, c.item_rows([r for r in rows if r.is_open], 25), "No pending approvals."),
    ]


def _v_master_admin(c):
    masters = frappe.get_all(
        "Compliance",
        fields=["name", "compliance_name", "department", "project", "compliance_company",
                "department_head", "recurrence", "start_date", "is_active"],
        limit_page_length=100000,
    )
    rule_dt = frappe.get_meta("Compliance").get_field("evidence_rules").options
    with_rules = {x.parent for x in frappe.get_all(rule_dt, filters={"parenttype": "Compliance"},
                                                   fields=["parent"], limit_page_length=100000)}
    assign_dt = frappe.get_meta("Compliance").get_field("assignments").options
    assignments = frappe.get_all(assign_dt, filters={"parenttype": "Compliance"},
                                 fields=["parent", "role", "user"], limit_page_length=100000)
    has_resp = {a.parent for a in assignments if a.role in ("Responsible Person", "Responsible", "Owner") and a.user}
    has_rev = {a.parent for a in assignments if a.role in ("Reviewer", "Checker") and a.user}

    missing = []
    for m in masters:
        gaps = [lbl for lbl, ok in (
            ("Responsible", m.name in has_resp), ("Reviewer", m.name in has_rev), ("Dept Head", m.department_head),
            ("Recurrence", m.recurrence), ("Start Date", m.start_date), ("Evidence rule", m.name in with_rules)) if not ok]
        if gaps:
            missing.append([_link(m.compliance_name or m.name, m.name, "Compliance"), ", ".join(gaps)])
    seen, dups = {}, []
    for m in masters:
        key = ((m.compliance_name or "").strip().lower(), m.department, m.project, m.compliance_company)
        seen.setdefault(key, []).append(m.name)
    for k, v in seen.items():
        if len(v) > 1:
            dups.append([k[0], ", ".join(v)])
    unassigned = [r for r in c.open() if not r.responsible_person]
    people = {}
    for r in c.open():
        for u in {r.responsible_person, r.backup_owner, r.reviewer}:
            if u:
                people.setdefault(u, 0)
                people[u] += 1
    inactive = []
    if people:
        for u in frappe.get_all("User", filters={"name": ["in", list(people)], "enabled": 0}, fields=["name"]):
            inactive.append([u.name, people[u.name]])
    usage = {}
    for r in c.rows:
        usage[r.title] = usage.get(r.title, 0) + 1
    usage_rows = sorted(usage.items(), key=lambda x: -x[1])[:10]
    kpis = [
        _kpi("Compliance masters", len(masters), "blue"),
        _kpi("Active", len([m for m in masters if m.is_active]), "green"),
        _kpi("Missing configuration", len(missing), "amber" if missing else "green"),
        _kpi("Duplicates", len(dups), "red" if dups else "green"),
        _kpi("Unassigned obligations", len(unassigned), "red" if unassigned else "green"),
        _kpi("Inactive users with open records", len(inactive), "red" if inactive else "green"),
    ]
    return [
        {"type": "kpis", "items": kpis},
        _table("Missing configurations", ["Compliance", "Missing"], missing[:20], "All masters are fully configured."),
        _table("Possible duplicates", ["Compliance", "Records"], dups, "No duplicates."),
        _table("Unassigned obligations", ITEM_COLS, c.item_rows(unassigned), "Every open record has an owner."),
        _table("Inactive users with open records", ["User", "Open records"], inactive, "None."),
        _table("Template usage (Requests per Compliance)", ["Compliance", "Requests"], [[k, v] for k, v in usage_rows],
               "No Requests yet."),
        _table("Change log (latest)", ["DocType", "Record", "By", "When"],
               _recent_versions(["Compliance", "Compliance Department", "Compliance Project",
                                 "Compliance Category", "Compliance Company", "Evidence Type"]), "No changes recorded."),
    ]


BUILDERS = {
    "master_admin": _v_master_admin,
    "leadership": _v_leadership,
    "chairman_office": _v_chairman_office,
    "central": _v_central,
    "unit_head": _v_unit_head,
    "dept_head": _v_dept_head,
    "project_head": _v_project_head,
    "responsible": _v_responsible,
}


@frappe.whitelist()
def get_dashboard(view=None):
    user = frappe.session.user
    avail = _available_views(user)
    if not avail:
        return {"views": [], "message": _("No compliance role is assigned to you, so there is no dashboard to show.")}
    keys = [v[0] for v in avail]
    view = view if view in keys else keys[0]
    label = [v[1] for v in avail if v[0] == view][0]
    ctx = Ctx(user)
    return {
        "views": [{"key": v[0], "label": v[1]} for v in avail],
        "view": view,
        "title": label,
        "widgets": BUILDERS[view](ctx),
        "generated": frappe.utils.format_datetime(now_datetime()),
    }
