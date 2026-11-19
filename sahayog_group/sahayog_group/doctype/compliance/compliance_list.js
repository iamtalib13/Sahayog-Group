frappe.provide("frappe.listview_settings");

frappe.listview_settings["Compliance"] = {
	add_fields: ["compliance_name", "risk_tier", "is_active", "department", "category"],
	formatters: {
		risk_tier(val) {
			const colors = {
				Critical: "purple",
				High: "red",
				Medium: "yellow",
				Low: "green",
			};
			if (!val) return "";
			const color = colors[val] || "gray";
			return `<span class="indicator-pill ${color}">${__(val)}</span>`;
		},
	},
	button: {
		show(doc) {
			return true;
		},
		get_label(doc) {
			return `<span class="indicator-pill orange" style="margin-right: 4px;"></span>Pending`;
		},
		get_description(doc) {
			return __("View pending requests");
		},
		action(doc) {
			const title = doc.compliance_name || doc.name;
			show_pending_requests_dialog(doc.name, title);
		},
	},
	refresh(listview) {
		reposition_action_buttons(listview);
	},
	post_render(listview) {
		reposition_action_buttons(listview);
	},
};

function reposition_action_buttons(listview) {
	// Move native action button column from end to immediately after checkbox (first position)
	listview.$result.find(".list-row-container").each(function () {
		const $row = $(this);
		const $btnCol = $row.find(".btn-action").closest(".list-row-col");
		const $checkbox = $row.find(".list-row-checkbox");
		if ($btnCol.length && $checkbox.length && !$btnCol.hasClass("repositioned-first")) {
			$btnCol.addClass("repositioned-first").css({ "margin-right": "12px", "min-width": "95px" });
			$btnCol.insertAfter($checkbox);
		}
	});

	// Move header column placeholder
	const $headerLeft = listview.$result.find(".list-row-head .level-left");
	if ($headerLeft.length && !$headerLeft.find(".head-action-first").length) {
		const $headCheckbox = $headerLeft.find(".list-check-all");
		const $headCol = $(`
			<div class="list-row-col head-action-first" style="min-width: 95px; max-width: 110px; margin-right: 12px; font-weight: 600; font-size: 12px;">
				${__("Requests")}
			</div>
		`);
		if ($headCheckbox.length) {
			$headCol.insertAfter($headCheckbox);
		} else {
			$headerLeft.prepend($headCol);
		}
	}

	// Update counts dynamically
	const names = (listview.data || []).map((d) => d.name);
	if (!names.length) return;

	frappe.call({
		method: "sahayog_group.sahayog_group.doctype.compliance.compliance.get_pending_requests_summary",
		args: { compliance_names: names },
		callback(r) {
			const summary = r.message || {};
			listview.$result.find(".btn-action[data-name]").each(function () {
				const $btn = $(this);
				const name = $btn.attr("data-name");
				const count = summary[name] ? summary[name].length : 0;
				const color = count > 0 ? "orange" : "gray";
				const text = count > 0 ? `${count} Pending` : `0 Pending`;
				$btn.html(`<span class="indicator-pill ${color}" style="margin-right: 4px;"></span>${text}`);
			});
		},
	});
}

function show_pending_requests_dialog(compliance_id, compliance_title) {
	frappe.call({
		method: "sahayog_group.sahayog_group.doctype.compliance.compliance.get_pending_requests_summary",
		args: { compliance_names: [compliance_id] },
		freeze: true,
		freeze_message: __("Loading Pending Requests..."),
		callback(r) {
			const summary = r.message || {};
			const list = summary[compliance_id] || [];

			let contentHtml = "";
			if (!list.length) {
				contentHtml = `
					<div class="text-center text-muted" style="padding: 30px 15px;">
						<i class="fa fa-check-circle" style="font-size: 32px; color: var(--green-500, #28a745); margin-bottom: 10px;"></i>
						<p style="font-size: 13px; margin: 0;">No pending requests! All obligations for this compliance are up-to-date.</p>
					</div>
				`;
			} else {
				const rows = list
					.map((item) => {
						const statusColor = get_status_color(item.status);
						return `
						<tr>
							<td style="font-weight: 600;"><a href="/desk/compliance-request/${item.name}" target="_blank">${item.name}</a></td>
							<td><span class="indicator-pill ${statusColor}">${item.status}</span></td>
							<td>${item.due_date}</td>
							<td>${item.responsible_person}</td>
							<td>${item.reviewer}</td>
						</tr>
					`;
					})
					.join("");

				contentHtml = `
					<div style="max-height: 400px; overflow-y: auto;">
						<table class="table table-bordered table-hover" style="margin-bottom: 0; font-size: 12px;">
							<thead style="background: var(--table-header-bg, #f4f5f7);">
								<tr>
									<th>Request ID</th>
									<th>Status</th>
									<th>Due Date</th>
									<th>Responsible</th>
									<th>Reviewer</th>
								</tr>
							</thead>
							<tbody>
								${rows}
							</tbody>
						</table>
					</div>
				`;
			}

			const d = new frappe.ui.Dialog({
				title: __("Pending Requests: {0}", [compliance_title]),
				size: "large",
				fields: [
					{
						fieldname: "html_content",
						fieldtype: "HTML",
						options: contentHtml,
					},
				],
				primary_action_label: __("Open All in Compliance Request"),
				primary_action() {
					d.hide();
					frappe.set_route("List", "Compliance Request", { compliance: compliance_id });
				},
			});

			d.show();
		},
	});
}

function get_status_color(status) {
	const map = {
		Overdue: "red",
		"Blocked / At Risk": "purple",
		"Action Required": "orange",
		"In Progress": "cyan",
		Upcoming: "blue",
		Draft: "gray",
		"Application Submitted": "yellow",
		"Awaiting Authority / Third Party": "yellow",
		"Completion Submitted": "cyan",
		"Closed / Completed": "green",
	};
	return map[status] || "gray";
}
