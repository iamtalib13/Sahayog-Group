"""One-time helpers for moving alert settings from Compliance Settings into each Compliance (Settings tab)."""

import frappe

DEFAULT_DAYS = {
    "critical": [90, 60, 30, 15, 5],
    "high": [60, 30, 15, 5],
    "medium": [30, 15],
    "low": [30, 7],
}


def copy_settings_to_compliance():
    """Copy the Risk Tier based alert settings into every Compliance that has none yet (prints FAILED on a problem)."""
    if not frappe.db.exists("DocType", "Compliance Settings"):
        print("Compliance Settings no longer exists, nothing to copy.")
        return
    s = frappe.get_doc("Compliance Settings")
    for name in frappe.get_all("Compliance", pluck="name"):
        c = frappe.get_doc("Compliance", name)
        if c.get("alert_days"):
            print("already has alert days:", name)
            continue
        key = (c.risk_tier or "Medium").lower()
        days = []
        for row in s.get(key + "_alert_days") or []:
            d = frappe.db.get_value("Alert Day", row.alert_day, "days")
            if d:
                days.append(int(d))
        if not days:
            days = list(DEFAULT_DAYS.get(key, DEFAULT_DAYS["medium"]))
        c.set("alert_days", [{"days": d} for d in sorted(set(days), reverse=True)])
        for f in ("responsible", "dept_head", "unit_head", "reviewer", "ceo"):
            c.set("notify_" + f, 1 if s.get("{0}_notify_{1}".format(key, f)) else 0)
        c.notify_role = s.get(key + "_notify_role")
        c.alert_urgent = 1 if s.get(key + "_urgent") else 0
        c.overdue_grace_days = int(s.overdue_grace_days or 0)
        c.acknowledgement_window_days = int(s.acknowledgement_window_days or 2)
        c.flags.ignore_permissions = True
        try:
            c.save()
            print("copied:", name, c.risk_tier, sorted(set(days), reverse=True))
        except Exception as e:
            print("FAILED:", name, str(e)[:200])
    frappe.db.commit()


def remove_old_doctypes():
    for dt in ("Compliance Settings", "Alert Day Item", "Alert Day"):
        if frappe.db.exists("DocType", dt):
            try:
                frappe.delete_doc("DocType", dt, force=True, ignore_permissions=True)
                print("deleted DocType:", dt)
            except Exception as e:
                print("could not delete", dt, "-", str(e)[:200])
        else:
            print("already gone:", dt)
    frappe.db.commit()


def clean_sidebar():
    parent = frappe.db.get_value("Sidebar Item", {"parenttype": "Custom Sidebar", "link_to": "Compliance Request"}, "parent")
    if not parent:
        print("sidebar not found, nothing changed")
        return
    doc = frappe.get_doc("Custom Sidebar", parent)
    keep = [r for r in doc.sidebar_items if r.link_to not in ("Compliance Settings", "Alert Day")]
    if len(keep) == len(doc.sidebar_items):
        print("sidebar already clean")
        return
    doc.sidebar_items = keep
    for i, r in enumerate(doc.sidebar_items, 1):
        r.idx = i
    doc.flags.ignore_permissions = True
    doc.save()
    frappe.db.commit()
    frappe.clear_cache()
    print("sidebar cleaned")
