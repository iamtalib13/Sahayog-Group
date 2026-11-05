// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

frappe.ui.form.on("Compliance", {
	refresh(frm) {
		load_requests_table(frm);
	},
	request_tab(frm) {
		load_requests_table(frm);
	},
});

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
