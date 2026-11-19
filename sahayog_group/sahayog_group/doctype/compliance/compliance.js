// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Compliance", {
	refresh(frm) {
		load_requests_table(frm);
		
	},
	department(frm) {
		fill_department_head(frm);
	},
	before_save(frm) {
		frm._was_new = frm.is_new();
	},
	after_save(frm) {
		if (frm._was_new && frm.doc.is_active && is_master()) {
			frm._was_new = false;
			frappe.confirm(
				__("Do you want to pre-create records in advance for this compliance?"),
				() => call_precreate("precreate_ask", { answer: "Yes" }, frm),
				() => call_precreate("precreate_ask", { answer: "No" }, frm)
			);
		}
	},
	request_tab(frm) {
		load_requests_table(frm);
	},
});

const PRECREATE = "sahayog_group.sahayog_group.doctype.compliance.compliance.";

function is_master() {
	return frappe.user.has_role("System Manager") || frappe.user.has_role("Compliance Master Admin");
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
