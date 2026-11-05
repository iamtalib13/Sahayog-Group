frappe.listview_settings["Compliance"] = {
	formatters: {
		risk_tier(val) {
			const colors = {
				"Critical": "purple",
				"High": "red",
				"Medium": "yellow",
				"Low": "green",
			};
			if (!val) return "";
			const color = colors[val] || "gray";
			return `<span class="indicator-pill ${color}">${__(val)}</span>`;
		},
	},
};
