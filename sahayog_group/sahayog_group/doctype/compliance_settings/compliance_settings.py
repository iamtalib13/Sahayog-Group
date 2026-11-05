import frappe
from frappe import _
from frappe.model.document import Document

DEFAULT_DAYS = [120, 90, 60, 30, 15, 7, 5]
DEFAULT_TIER_DAYS = {
    "critical": [90, 60, 30, 15, 5],
    "high": [60, 30, 15, 5],
    "medium": [30, 15],
    "low": [30, 7],
}
URGENT_BY_DEFAULT = ("critical", "high")
RECIPIENTS = ("responsible", "dept_head", "reviewer", "role")


class ComplianceSettings(Document):
    def validate(self):
        for key in DEFAULT_TIER_DAYS:
            table = self.get(f"{key}_alert_days") or []
            has_days = len(table) > 0
            has_recipient = any(self.get(f"{key}_notify_{r}") for r in RECIPIENTS)
            if has_days and not has_recipient:
                frappe.throw(_("{0} Risk: choose at least one person or role to notify.").format(key.title()))

        if (self.overdue_grace_days or 0) < 0:
            frappe.throw(_("Overdue Grace Days cannot be negative."))
        if (self.acknowledgement_window_days or 0) < 1:
            frappe.throw(_("Acknowledgement Window Days must be 1 or more."))


def get_alert_config(risk_tier):
    """Used by the daily alert job: days, recipients and urgency for one Risk Tier."""
    key = (risk_tier or "").lower()
    s = frappe.get_cached_doc("Compliance Settings")
    days = []
    for row in s.get(f"{key}_alert_days") or []:
        val = frappe.db.get_value("Alert Day", row.alert_day, "days")
        if val:
            days.append(int(val))

    return {
        "days": sorted(days, reverse=True),
        "responsible": bool(s.get(f"{key}_notify_responsible")),
        "dept_head": bool(s.get(f"{key}_notify_dept_head")),
        "reviewer": bool(s.get(f"{key}_notify_reviewer")),
        "role": s.get(f"{key}_notify_role"),
        "urgent": bool(s.get(f"{key}_urgent")),
    }


def seed_defaults():
    """Seed starting Alert Day records and default alert days in Compliance Settings."""
    for d in DEFAULT_DAYS:
        if not frappe.db.exists("Alert Day", str(d)):
            frappe.get_doc({"doctype": "Alert Day", "days": d}).insert(ignore_permissions=True)

    s = frappe.get_doc("Compliance Settings")
    for key, days in DEFAULT_TIER_DAYS.items():
        fieldname = f"{key}_alert_days"
        if not s.get(fieldname):
            s.set(fieldname, [{"alert_day": str(d)} for d in days])
        s.set(f"{key}_notify_responsible", 1)
        s.set(f"{key}_notify_dept_head", 1)
        s.set(f"{key}_notify_reviewer", 0)
        s.set(f"{key}_urgent", 1 if key in URGENT_BY_DEFAULT else 0)
    s.overdue_grace_days = 2
    s.acknowledgement_window_days = 2
    s.save(ignore_permissions=True)
    frappe.db.commit()
    print("MultiSelect Alert Settings seeded successfully")
