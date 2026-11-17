// Compliance Home: role-wise dashboard page (BRD section 12)
var CHOME_API = "sahayog_group.sahayog_group.dashboard.get_dashboard";
var CHOME_TONES = {
	red: "rgba(220,38,38,.14)", amber: "rgba(217,119,6,.16)", green: "rgba(22,163,74,.14)",
	blue: "rgba(37,99,235,.12)", grey: "rgba(120,120,120,.14)",
};

function chome_cell(c) {
	const esc = frappe.utils.escape_html;
	if (c === null || c === undefined) return "-";
	if (typeof c !== "object") return esc(String(c));
	let text = esc(String(c.text));
	if (c.link) text = '<a class="cdash-open" data-dt="' + esc(c.link[0]) + '" data-name="' + esc(c.link[1]) + '">' + text + "</a>";
	if (c.tone) text = '<span class="cdash-pill" style="background:' + (CHOME_TONES[c.tone] || CHOME_TONES.grey) + ';">' + text + "</span>";
	return text;
}

function chome_html(data) {
	const esc = frappe.utils.escape_html;
	let h = `<style>
		.cdash{padding:6px 2px}
		.cdash-head{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:14px}
		.cdash-title{font-size:16px;font-weight:600;margin-right:auto}
		.cdash-tab{padding:4px 12px;border:1px solid var(--border-color);border-radius:16px;cursor:pointer;font-size:12px}
		.cdash-tab.active{background:var(--primary);color:#fff;border-color:var(--primary)}
		.cdash-kpis{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-bottom:18px}
		.cdash-kpi{border:1px solid var(--border-color);border-radius:8px;padding:10px 12px}
		.cdash-kpi.click{cursor:pointer}
		.cdash-kpi .v{font-size:24px;font-weight:600;line-height:1.2}
		.cdash-kpi .l{font-size:12px;color:var(--text-muted)}
		.cdash-card{border:1px solid var(--border-color);border-radius:8px;margin-bottom:16px;overflow:hidden}
		.cdash-card h6{margin:0;padding:10px 12px;font-weight:600;border-bottom:1px solid var(--border-color)}
		.cdash-card table{width:100%;font-size:12px}
		.cdash-card th{padding:6px 12px;color:var(--text-muted);font-weight:500;text-align:left}
		.cdash-card td{padding:6px 12px;border-top:1px solid var(--border-color)}
		.cdash-pill{padding:1px 8px;border-radius:10px;font-size:11px}
		.cdash-bar{display:flex;align-items:center;gap:10px;padding:5px 12px;font-size:12px}
		.cdash-bar .lab{width:90px;color:var(--text-muted)}
		.cdash-bar .track{flex:1;height:10px;background:rgba(120,120,120,.15);border-radius:5px}
		.cdash-bar .fill{height:10px;border-radius:5px;background:var(--primary)}
		.cdash-empty{padding:12px;color:var(--text-muted);font-size:12px}
	</style><div class="cdash">`;

	h += '<div class="cdash-head"><div class="cdash-title">' + esc(data.title || __("Dashboard")) + "</div>";
	(data.views || []).forEach((v) => {
		h += '<span class="cdash-tab ' + (v.key === data.view ? "active" : "") + '" data-view="' + esc(v.key) + '">' + esc(v.label) + "</span>";
	});
	h += '<span class="cdash-tab cdash-refresh">' + __("Refresh") + "</span></div>";

	if (!data.views || !data.views.length) {
		return h + '<div class="cdash-empty">' + esc(data.message || "") + "</div></div>";
	}

	(data.widgets || []).forEach((w, i) => {
		if (w.type === "kpis") {
			h += '<div class="cdash-kpis">';
			w.items.forEach((k, j) => {
				h += '<div class="cdash-kpi ' + (k.filters ? "click" : "") + '" data-w="' + i + '" data-k="' + j + '" style="background:' +
					(CHOME_TONES[k.tone] || CHOME_TONES.blue) + ';" title="' + esc(k.hint || "") + '"><div class="v">' + esc(String(k.value)) +
					'</div><div class="l">' + esc(k.label) + "</div></div>";
			});
			h += "</div>";
		} else if (w.type === "table") {
			h += '<div class="cdash-card"><h6>' + esc(w.title) + "</h6>";
			if (!w.rows.length) {
				h += '<div class="cdash-empty">' + esc(w.empty || "") + "</div>";
			} else {
				h += "<table><thead><tr>" + w.columns.map((c) => "<th>" + esc(c) + "</th>").join("") + "</tr></thead><tbody>";
				w.rows.forEach((row) => { h += "<tr>" + row.map((c) => "<td>" + chome_cell(c) + "</td>").join("") + "</tr>"; });
				h += "</tbody></table>";
			}
			h += "</div>";
		} else if (w.type === "bars") {
			const max = Math.max.apply(null, w.items.map((x) => x.value).concat([1]));
			h += '<div class="cdash-card"><h6>' + esc(w.title) + "</h6>";
			w.items.forEach((x) => {
				h += '<div class="cdash-bar"><span class="lab">' + esc(x.label) + '</span><span class="track"><span class="fill" style="display:block;width:' +
					Math.round((100 * x.value) / max) + '%"></span></span><b>' + x.value + "</b></div>";
			});
			h += "</div>";
		}
	});
	h += '<div class="text-muted" style="font-size:11px;">' + __("Updated") + " " + esc(data.generated || "") + "</div></div>";
	return h;
}


frappe.pages["compliance-home"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Home"), single_column: true });
	const $body = $('<div class="cdash-host"></div>').appendTo(page.main);
	const state = { view: "", data: null };

	const load = (view) => {
		$body.html('<div class="text-muted" style="padding:20px;">' + __("Loading dashboard...") + "</div>");
		frappe.call({
			method: CHOME_API,
			args: { view: view || state.view || "" },
			callback(r) {
				const data = r && r.message;
				if (!data) return;
				state.view = data.view;
				state.data = data;
				$body.html(chome_html(data));
				$body.find(".cdash-tab[data-view]").on("click", function () { load($(this).data("view")); });
				$body.find(".cdash-refresh").on("click", () => load());
				$body.find(".cdash-open").on("click", function () {
					frappe.set_route("Form", $(this).data("dt"), $(this).data("name"));
				});
				$body.find(".cdash-kpi.click").on("click", function () {
					const k = state.data.widgets[$(this).data("w")].items[$(this).data("k")];
					frappe.route_options = k.filters;
					frappe.set_route("List", "Compliance Request");
				});
			},
		});
	};
	wrapper.chome_reload = load;
	load();
};

frappe.pages["compliance-home"].on_page_show = function (wrapper) {
	if (wrapper.chome_reload && wrapper.chome_loaded) wrapper.chome_reload();
	wrapper.chome_loaded = true;
};
