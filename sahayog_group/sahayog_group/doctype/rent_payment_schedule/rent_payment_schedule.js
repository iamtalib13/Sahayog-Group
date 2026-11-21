// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Rent Payment Schedule", {
	refresh(frm) {
		if (frm.is_new()) return;

		const user = frappe.session.user;
		const is_admin = frappe.user_roles.includes("Compliance Master Admin") || frappe.user_roles.includes("System Manager");

		// Button for Admin to trigger invoice verification
		if (frm.doc.status === "Invoices Uploaded" && is_admin) {
			frm.add_custom_button(__("Approve Schedule"), () => {
				frappe.confirm(__("Are you sure you want to approve this Rent Payment Schedule?"), () => {
					frm.set_value("status", "Approved");
					frm.set_value("approved_by", user);
					frm.set_value("approved_on", frappe.datetime.now_datetime());
					frm.save();
				});
			}, __("Actions"));

			frm.add_custom_button(__("Reject Schedule"), () => {
				frappe.prompt([
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Rejection Reason"), reqd: 1 }
				], (v) => {
					frm.set_value("status", "Rejected");
					frm.set_value("rejection_reason", v.reason);
					frm.save();
				}, __("Reject Rent Schedule"), __("Reject"));
			}, __("Actions"));
		}
	},
});
