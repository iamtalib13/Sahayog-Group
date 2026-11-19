// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Compliance", {
	refresh(frm) {
		load_requests_table(frm);
		setup_precreate(frm);
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

function call_precreate(method, args, frm, after) {
	frappe.call({
		method: PRECREATE + method,
		args: Object.assign({ compliance: frm.doc.name }, args),
		freeze: true,
		callback(r) {
			if (r && r.message) {
				frappe.show_alert({ message: r.message.message, indicator: "green" }, 2);
			}
			frm.reload_doc();
			if (after) after(r);
		},
	});
}

function setup_precreate(frm) {
	if (frm.is_new() || !frm.doc.is_active) return;
	const master = is_master();
	const owner = is_owner_user(frm);
	if (!master && !owner) return;

	frm.add_custom_button(__("Pre-create Records Request"), () => open_precreate_dialog(frm, master));

	const status = frm.doc.precreate_status;
	if (status === "Asked" && owner) {
		frm.dashboard.set_headline_alert(
			__("Do you want to pre-create records for this compliance? Click 'Pre-create Records Request'."), "blue"
		);
	}
	if (status === "Requested" && master) {
		frm.dashboard.set_headline_alert(
			__("Pre-create request: {0} record(s) requested by {1}.", [frm.doc.precreate_count, frm.doc.precreate_requested_by]),
			"orange"
		);
		frm.add_custom_button(__("Accept"), () => {
			call_precreate("precreate_decide", { decision: "Accept" }, frm);
		}, __("Pre-create Request"));
		frm.add_custom_button(__("Reject"), () => {
			call_precreate("precreate_decide", { decision: "Reject" }, frm);
		}, __("Pre-create Request"));
	}
}

function open_precreate_dialog(frm, master) {
	if (!frm.doc.start_date) {
		frappe.msgprint(__("Set the Start Date first."));
		return;
	}
	const d = new frappe.ui.Dialog({
		title: master ? __("Pre-create Records") : __("Pre-create Records Request"),
		fields: [
			{ fieldname: "recurrence", fieldtype: "Data", label: __("Recurrence"), default: frm.doc.recurrence, read_only: 1 },
			{ fieldname: "count", fieldtype: "Int", label: __("How many records to create in advance?"), reqd: 1 },
		],
		primary_action_label: master ? __("Create Records") : __("Send Request"),
		primary_action(values) {
			d.hide();
			call_precreate("precreate_send_request", { count: values.count }, frm);
		},
	});
	d.show();
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
