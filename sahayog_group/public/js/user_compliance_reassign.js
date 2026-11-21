frappe.ui.form.on("User", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Reassign Compliance"), () => {
			frappe.call({
				method: "sahayog_group.sahayog_group.doctype.compliance.compliance.get_user_open_compliance_count",
				args: { user: frm.doc.name },
				callback(r) {
					const counts = r.message || { master_count: 0, request_count: 0 };
					frappe.prompt([
						{
							fieldname: "info",
							fieldtype: "HTML",
							options: `<div class="alert alert-info" style="font-size:12px; margin-bottom:10px;">
								User <b>${frm.doc.name}</b> has <b>${counts.master_count}</b> active master assignments and <b>${counts.request_count}</b> open compliance requests.
							</div>`,
						},
						{
							fieldname: "to_user",
							fieldtype: "Link",
							options: "User",
							label: __("Reassign Everything To"),
							reqd: 1,
							get_query: () => ({ filters: { enabled: 1, name: ["!=", frm.doc.name] } }),
						},
						{
							fieldname: "reason",
							fieldtype: "Small Text",
							label: __("Reason / Handover Notes"),
							default: "Employee exit / role transfer handover",
							reqd: 1,
						},
					], (v) => {
						frappe.call({
							method: "sahayog_group.sahayog_group.doctype.compliance.compliance.bulk_reassign_user_obligations",
							args: {
								from_user: frm.doc.name,
								to_user: v.to_user,
								reason: v.reason,
							},
							freeze: true,
							freeze_message: __("Reassigning all compliance obligations..."),
							callback(res) {
								const d = res.message;
								frappe.msgprint(__("Successfully reassigned {0} master assignments and {1} active requests to {2}.", [
									d.reassigned_assignments,
									d.reassigned_requests,
									v.to_user
								]));
							},
						});
					}, __("Bulk Reassign Compliance Obligations"), __("Reassign All"));
				},
			});
		}, __("Actions"));
	},
});
