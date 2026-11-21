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

frappe.ui.form.on("Compliance Landlord Item", {
	landlords_add(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const other_total = (frm.doc.landlords || [])
			.filter((r) => r.name !== row.name)
			.reduce((acc, r) => acc + flt(r.share_ratio), 0);
		const remaining = Math.max(0, 100 - other_total);
		frappe.model.set_value(cdt, cdn, "share_ratio", remaining);
	},
	share_ratio(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const current_val = flt(row.share_ratio);
		const other_total = (frm.doc.landlords || [])
			.filter((r) => r.name !== row.name)
			.reduce((acc, r) => acc + flt(r.share_ratio), 0);
		const max_allowed = Math.max(0, 100 - other_total);

		if (current_val > max_allowed) {
			frappe.msgprint({
				message: __("Share ratio cannot exceed remaining limit of {0}%. Value reset to {0}%.", [max_allowed]),
				indicator: "orange",
				title: __("Share Ratio Limit Exceeded"),
			});
			frappe.model.set_value(cdt, cdn, "share_ratio", max_allowed);
		} else if (current_val < 0) {
			frappe.msgprint({
				message: __("Share ratio cannot be negative."),
				indicator: "red",
				title: __("Invalid Share Ratio"),
			});
			frappe.model.set_value(cdt, cdn, "share_ratio", 0);
		}
	},
	landlord_pan(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.landlord_pan) return;
		const pan = row.landlord_pan.trim().toUpperCase();
		frappe.model.set_value(cdt, cdn, "landlord_pan", pan);

		const panRegex = /^[A-Z]{5}[0-9]{4}[A-Z]{1}$/;
		if (!panRegex.test(pan)) {
			frappe.msgprint({
				message: __("Invalid Landlord PAN '{0}'. Format must be 5 letters, 4 digits, 1 letter (e.g. ABCDE1234F).", [pan]),
				indicator: "red",
				title: __("Invalid PAN"),
			});
		}
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
		frappe.db.get_value("User", head, "full_name").then((res) => {
			const fullName = (res && res.message && res.message.full_name) || head;
			const row = (frm.doc.assignments || []).find((x) => x.role === "Department Head");
			if (row) {
				frappe.model.set_value(row.doctype, row.name, "user", head);
				frappe.model.set_value(row.doctype, row.name, "name1", fullName);
			} else {
				frm.add_child("assignments", { role: "Department Head", user: head, name1: fullName });
			}
			frm.refresh_field("assignments");
		});
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


frappe.ui.form.on("Compliance", {
	refresh(frm) {
		const field = frm.fields_dict.landlords;
		const grid = field && field.grid;
		if (!grid) return;
		grid.update_docfield_property("landlord_pan", "length", 10);
		grid.update_docfield_property("sahayog_account_no", "length", 15);
	},
});

frappe.ui.form.on("Compliance Landlord Item", {
	landlord_pan(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const pan = String(row.landlord_pan || "").toUpperCase();
		if (pan !== (row.landlord_pan || "")) frappe.model.set_value(cdt, cdn, "landlord_pan", pan);
		if (pan && !/^[A-Z]{5}[0-9]{4}[A-Z]$/.test(pan)) {
			frappe.show_alert({
				message: __("Landlord PAN must be 10 characters: 5 letters, 4 digits, 1 letter (for example ABCDE1234F)."),
				indicator: "red",
			}, 7);
		}
	},
	sahayog_account_no(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		const value = String(row.sahayog_account_no || "");
		if (value && value.length !== 15) {
			frappe.show_alert({
				message: __("Sahayog Savings A/c No must be exactly 15 digits (you entered {0}).", [value.length]),
				indicator: "red",
			}, 7);
		}
	},
});
