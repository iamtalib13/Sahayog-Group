// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Compliance Request", {
	refresh(frm) {
		if (frm.is_new()) return;

		const user = frappe.session.user;
		const d = frm.doc;
		const s = d.status;
		const is_owner = [d.responsible_person, d.backup_owner].includes(user);
		const is_reviewer = d.reviewer === user;
		const is_manager = [d.reviewer, d.department_head].includes(user);
		const path = "sahayog_group.sahayog_group.doctype.compliance_request.compliance_request.";

		const call = (method, args) => {
			frappe.call({
				method: path + method,
				args: Object.assign({ name: frm.doc.name }, args),
				freeze: true,
				callback: () => frm.reload_doc(),
			});
		};
		const guard = () => {
			if (frm.is_dirty()) {
				frappe.msgprint(__("Please save the record first."));
				return false;
			}
			return true;
		};
		const add = (label, handler, primary) => {
			frm.add_custom_button(__(label), () => { if (guard()) handler(); });
			if (primary && frm.change_custom_button_type) {
				frm.change_custom_button_type(__(label), null, "primary");
			}
		};
		const simple = (label, primary) => add(label, () => call("run_action", { action: label }), primary);
		const asking = (label, fields, primary) => add(label, () => {
			frappe.prompt(fields, (v) => call("run_action", Object.assign({ action: label }, v)), __(label), __(label));
		}, primary);

		const working = ["In Progress", "Application Submitted", "Awaiting Authority / Third Party"];

		if (is_owner) {
			if (["Draft", "Upcoming", "Action Required"].includes(s)) simple("Start Work", true);
			if (s === "In Progress") simple("Submit Application");
			if (s === "Application Submitted") simple("Mark Awaiting Authority");
			if (working.includes(s)) {
				simple("Request Closure", s !== "Application Submitted" && s !== "In Progress" ? true : false);
				asking("Mark Blocked", [
					{ fieldname: "blocker", fieldtype: "Small Text", label: __("Blocker"), reqd: 1 },
					{ fieldname: "next_action", fieldtype: "Small Text", label: __("Next Action (mitigation plan)"), reqd: 1 },
				]);
			}
			if (s === "Blocked / At Risk") simple("Resume Work", true);
		}

		if (is_reviewer && s === "Completion Submitted") {
			simple("Approve", true);
			asking("Reject", [{ fieldname: "reason", fieldtype: "Small Text", label: __("Rejection Reason"), reqd: 1 }]);
		}

		if (is_manager && s === "Closed / Completed") {
			asking("Reopen", [{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason for Reopening"), reqd: 1 }]);
		}

		if (d.department_head === user && !["Closed / Completed", "Superseded / Inactive"].includes(s)) {
			add("Reassign", () => {
				frappe.prompt([
					{ fieldname: "new_responsible", fieldtype: "Link", options: "User", label: __("New Responsible Person"), reqd: 1 },
					{ fieldname: "new_backup", fieldtype: "Link", options: "User", label: __("New Backup Owner") },
					{ fieldname: "reason", fieldtype: "Small Text", label: __("Reason"), reqd: 1 },
				], (v) => call("reassign", v), __("Reassign"), __("Reassign"));
			});
		}
	},
});

// Default Due Date for a new Request (does not overwrite a date the user typed)
function set_default_due_date(frm) {
	if (!frm.is_new() || !frm.doc.compliance) return;
	if (frm.doc.due_date && frm.doc.due_date !== frm._auto_due_date) return;
	frappe.call({
		method: "sahayog_group.sahayog_group.doctype.compliance_request.compliance_request.get_default_due_date",
		args: { compliance: frm.doc.compliance },
		callback(r) {
			if (r.message) {
				frm._auto_due_date = r.message;
				frm.set_value("due_date", r.message);
			}
		},
	});
}

frappe.ui.form.on("Compliance Request", {
	compliance: set_default_due_date,
});
