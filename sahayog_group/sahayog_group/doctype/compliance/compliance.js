// Copyright (c) 2026, Talib Sheikh and contributors
// For license information, please see license.txt

// frappe.ui.form.on("Compliance", {
// 	refresh(frm) {

// 	},
// });

frappe.ui.form.on("Compliance", {
	risk_tier(frm) {
		frm.set_value("is_critical", frm.doc.risk_tier === "Critical" ? 1 : 0);
	},
});
