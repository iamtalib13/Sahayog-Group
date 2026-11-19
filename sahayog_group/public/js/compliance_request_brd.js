// BRD part 1 for Compliance Request: history buttons and evidence access log.
frappe.ui.form.on("Compliance Request", {
	refresh(frm) {
		if (frm.is_new()) return;
		const d = frm.doc;
		const api = "sahayog_group.sahayog_group.audit_controls.log_evidence_access";
		frm.add_custom_button(__("Audit Trail"), () => frappe.set_route("List", "Compliance Audit Log", { compliance_request: d.name }), __("History"));
		frm.add_custom_button(__("Evidence Versions"), () => frappe.set_route("List", "Evidence File Version", { compliance_request: d.name }), __("History"));

		const log = (file, action) => frappe.call({ method: api, args: { name: d.name, file_url: file || "", action: action } });
		if ((d.evidence_items || []).some((r) => r.file) && frm.__evidence_logged !== d.name) {
			frm.__evidence_logged = d.name;
			log(null, "Record Opened");
		}
		$(frm.wrapper).off("click.evlog").on("click.evlog", "a[href*='/files/']", function () {
			log($(this).attr("href"), "File Opened");
		});
	},
});

