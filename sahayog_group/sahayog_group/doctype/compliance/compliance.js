// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Compliance", {
	refresh(frm) {
		set_category_indicator(frm);
		load_requests_table(frm);
	},
	category(frm) {
		set_category_indicator(frm);
	},
	is_rent(frm) {
		if (frm.doc.is_rent) {
			frm.set_value("category", "Rent & Lease");
			if (!frm.doc.obligation_type) frm.set_value("obligation_type", "Agreement");
			if (!frm.doc.recurrence) frm.set_value("recurrence", "Monthly");
		}
	},
	department(frm) {
		fill_department_head(frm);
	},
	request_tab(frm) {
		load_requests_table(frm);
	},
});

function set_category_indicator(frm) {
	if (frm.doc.category) {
		frm.page.set_indicator(frm.doc.category, "blue");
	} else {
		frm.page.clear_indicator();
	}
}

function is_owner_user(frm) {
	return (frm.doc.assignments || []).some(
		(r) => ["Responsible Person", "Backup Owner"].includes(r.role) && r.user === frappe.session.user
	);
}

function fill_department_head(frm) {
	if (!frm.doc.department) return;
	frappe.db.get_value("Compliance Department", frm.doc.department, "department_head").then((r) => {
		const head = r && r.message && r.message.department_head;
		if (!head) return;
		const row = (frm.doc.assignments || []).find((x) => x.role === "Department Head");
		if (row) {
			frappe.model.set_value(row.doctype, row.name, "user", head);
		} else {
			frm.add_child("assignments", { role: "Department Head", user: head });
		}
		frm.refresh_field("assignments");
	});
}

function load_requests_table(frm) {
	if (!frm.fields_dict.html_filg) return;
	frappe.call({
		method: "sahayog_group.sahayog_group.doctype.compliance.compliance.get_requests_html",
		args: { compliance_name: frm.doc.name || "" },
		callback(r) {
			frm.fields_dict.html_filg.$wrapper.html((r && r.message) || "");
		},
	});
}
