import frappe
from frappe import _
from frappe.model.document import Document


class ComplianceProject(Document):
    def validate(self):
        self.project = (self.project or "").strip()
        exists = frappe.db.exists("Compliance Project", {
            "project": self.project,
            "company": self.company,
            "name": ["!=", self.name],
        })
        if exists:
            frappe.throw(
                _("Project {0} already exists for Company {1}.").format(self.project, self.company)
            )


@frappe.whitelist()
def get_project_readiness_html(project_name):
    """Render milestone dependency & critical path readiness table for project."""
    if not project_name:
        return ""

    compliances = frappe.get_all(
        "Compliance",
        filters={"project": project_name, "is_active": 1},
        fields=["name", "compliance_name", "department", "predecessor", "is_critical_path"],
        order_by="is_critical_path desc, compliance_name asc"
    )

    if not compliances:
        return "<div class='text-muted' style='padding:15px;'>" + _("No compliances linked to this project yet.") + "</div>"

    # Fetch latest requests for these compliances
    comp_names = [c.name for c in compliances]
    requests = frappe.get_all(
        "Compliance Request",
        filters={"compliance": ["in", comp_names]},
        fields=["name", "compliance", "status", "due_date", "responsible_person"],
        order_by="creation desc"
    )

    req_map = {}
    for r in requests:
        if r.compliance not in req_map:
            req_map[r.compliance] = r

    # Map compliance names for predecessor lookup
    comp_title_map = {c.name: c.compliance_name for c in compliances}

    rows = []
    for c in compliances:
        r = req_map.get(c.name)
        status = r.status if r else "Not Scheduled"
        due_date = str(r.due_date) if r and r.due_date else "-"
        responsible = r.responsible_person if r and r.responsible_person else "-"

        # Check predecessor status
        pred_label = "-"
        pred_blocked = False
        if c.predecessor:
            pred_name = comp_title_map.get(c.predecessor, c.predecessor)
            pred_req = req_map.get(c.predecessor)
            pred_status = pred_req.status if pred_req else "Pending"
            if pred_status != "Closed / Completed":
                pred_blocked = True
                pred_label = f"<span style='color:var(--red-500); font-weight:600;'>⚠ {pred_name} ({pred_status})</span>"
            else:
                pred_label = f"<span style='color:var(--green-500);'>✓ {pred_name}</span>"

        # Badge color
        color_map = {
            "Closed / Completed": "green",
            "In Progress": "blue",
            "Application Submitted": "blue",
            "Awaiting Authority / Third Party": "amber",
            "Blocked / At Risk": "red",
            "Overdue": "red",
            "Completion Submitted": "purple",
            "Exception Approved": "cyan",
        }
        badge_color = color_map.get(status, "gray")
        badge_html = f"<span class='indicator-pill {badge_color}'>{status}</span>"

        cp_badge = "<span class='indicator-pill red'>Critical Path</span>" if c.is_critical_path else "<span class='text-muted'>Standard</span>"
        if pred_blocked and status != "Closed / Completed":
            badge_html += " <span class='badge bg-warning text-dark' title='Predecessor not completed'>Predecessor Pending</span>"

        req_link = f"<a href='/app/compliance-request/{r.name}'>{r.name}</a>" if r else "-"

        rows.append(f"""
            <tr>
                <td><b><a href='/app/compliance/{c.name}'>{c.compliance_name}</a></b></td>
                <td>{c.department or '-'}</td>
                <td>{cp_badge}</td>
                <td>{pred_label}</td>
                <td>{due_date}</td>
                <td>{responsible}</td>
                <td>{badge_html}</td>
                <td>{req_link}</td>
            </tr>
        """)

    html = f"""
    <div style="border:1px solid var(--border-color); border-radius:8px; overflow:hidden; margin: 10px 0;">
        <table class="table table-bordered table-sm" style="margin:0; font-size:12px;">
            <thead style="background:var(--table-header-bg, #f8f9fa);">
                <tr>
                    <th>{_('Compliance / Milestone')}</th>
                    <th>{_('Department')}</th>
                    <th>{_('Type')}</th>
                    <th>{_('Predecessor Dependency')}</th>
                    <th>{_('Due Date')}</th>
                    <th>{_('Responsible Person')}</th>
                    <th>{_('Status')}</th>
                    <th>{_('Active Request')}</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """
    return html
