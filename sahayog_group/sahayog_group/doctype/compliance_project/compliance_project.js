// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Compliance Project", {
	refresh(frm) {
		load_readiness_table(frm);
	},
});

function load_readiness_table(frm) {
	if (frm.is_new() || !frm.fields_dict.readiness_html) return;
	frappe.call({
		method: "sahayog_group.sahayog_group.doctype.compliance_project.compliance_project.get_project_readiness_html",
		args: { project_name: frm.doc.name },
		callback(r) {
			frm.fields_dict.readiness_html.$wrapper.html(r.message || "");
		},
	});
}
