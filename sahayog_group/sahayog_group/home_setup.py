"""One-time setup: put "Home" at the top of the Compliance sidebar."""

import frappe


def add_home_sidebar():
    parent = frappe.db.get_value(
        "Sidebar Item", {"parenttype": "Custom Sidebar", "link_to": "Compliance Request"}, "parent"
    )
    if not parent:
        print("STOP: the Compliance sidebar was not found, nothing changed.")
        return
    doc = frappe.get_doc("Custom Sidebar", parent)
    if any(r.link_to == "compliance-home" for r in doc.sidebar_items):
        print("Home is already in the sidebar.")
        return
    doc.append("sidebar_items", {
        "label": "Home", "type": "Link", "link_type": "Page", "link_to": "compliance-home",
        "icon": "house", "collapsible": 1, "open_in_new_tab": 0,
    })
    rows = list(doc.sidebar_items)
    rows.insert(0, rows.pop())
    doc.sidebar_items = rows
    for i, r in enumerate(doc.sidebar_items, 1):
        r.idx = i
    doc.flags.ignore_permissions = True
    doc.save()
    frappe.db.commit()
    frappe.clear_cache()
    print("Home added to the sidebar ({0}).".format(parent))
