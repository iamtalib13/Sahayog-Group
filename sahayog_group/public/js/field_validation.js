const SYJ_LANDLORD_FIELDS = {
	landlord_name: "letters",
	landlord_pan: "pan",
	bank_name: "letters",
	sahayog_account_no: "digits:15",
	bank_account_no: "digits",
	ifsc_code: "ifsc",
	landlord_gstin: "gstin",
};

const SYJ_RULES = {
	Compliance: {
		compliance_name: "letters",
		issuing_authority: "letters",
		sol_id: "digits",
		branch_name: "letters",
	},
	"Compliance Category": { category: "letters" },
	"Compliance Company": { company: "letters" },
	"Compliance Department": { department: "letters" },
	"Compliance Project": { project: "letters" },
	"Evidence Type": { type_name: "letters" },
	"Compliance Landlord Item": SYJ_LANDLORD_FIELDS,
	"Rent Schedule Item": SYJ_LANDLORD_FIELDS,
	"Rent Payment Schedule": { sol_id: "digits", branch_name: "letters" },
	"Compliance Request": { application_reference_no: "alphanumeric" },
	"Evidence Item": { period: "alphanumeric", arn__reference_no: "alphanumeric" },
	"Evidence File Version": { period: "alphanumeric" },
};

const SYJ_FIELD_RULES = {};
Object.values(SYJ_RULES).forEach((fields) => {
	Object.entries(fields).forEach(([fieldname, rule]) => {
		SYJ_FIELD_RULES[fieldname] = rule;
	});
});

const SYJ_CONTROL_KEYS = [
	"Backspace",
	"Delete",
	"Tab",
	"Enter",
	"Escape",
	"ArrowLeft",
	"ArrowRight",
	"ArrowUp",
	"ArrowDown",
	"Home",
	"End",
	"PageUp",
	"PageDown",
	"Insert",
];

function syj_rule_parts(rule) {
	const [name, arg] = String(rule || "").split(":");
	return { name, max: arg ? Number(arg) : null };
}

function syj_char_allowed(rule, char, position) {
	const { name } = syj_rule_parts(rule);
	if (name === "letters") return !/\d/.test(char);
	if (name === "digits") return /[0-9]/.test(char);
	if (name === "alphanumeric") return /[\w\s.,/\-&'()]/u.test(char);
	if (name === "pan") {
		if (position >= 10) return false;
		if (position >= 5 && position <= 8) return /[0-9]/.test(char);
		return /[A-Za-z]/.test(char);
	}
	if (name === "ifsc") {
		if (position >= 11) return false;
		if (position <= 3) return /[A-Za-z]/.test(char);
		if (position === 4) return char === "0";
		return /[A-Za-z0-9]/.test(char);
	}
	if (name === "gstin") return position < 15 && /[A-Za-z0-9]/.test(char);
	return true;
}

function syj_clean_text(text, rule, position, available) {
	const { name, max } = syj_rule_parts(rule);
	let limit = available == null ? Infinity : available;
	if (max != null) limit = Math.min(limit, max);
	let out = "";
	for (const char of String(text || "")) {
		if (out.length >= limit) break;
		if (syj_char_allowed(rule, char, position + out.length)) out += char;
	}
	return name === "pan" || name === "ifsc" || name === "gstin" ? out.toUpperCase() : out;
}

function syj_input_rule(input) {
	return SYJ_FIELD_RULES[input.getAttribute("data-fieldname")];
}

$(document).on("keydown.syj_validation", "input[data-fieldname]", function (e) {
	const rule = syj_input_rule(this);
	if (!rule || e.ctrlKey || e.metaKey || e.altKey || e.isComposing) return;
	if (SYJ_CONTROL_KEYS.includes(e.key) || e.key.length !== 1) return;
	const start = this.selectionStart;
	const end = this.selectionEnd;
	const replacing = start !== end;
	const { max } = syj_rule_parts(rule);
	if (!replacing && max && (this.value || "").length >= max) {
		e.preventDefault();
		return;
	}
	if (!syj_char_allowed(rule, e.key, start)) e.preventDefault();
});

$(document).on("beforeinput.syj_validation", "input[data-fieldname]", function (e) {
	if (e.isComposing || e.inputType !== "insertText" || !e.data) return;
	const rule = syj_input_rule(this);
	if (!rule) return;
	const start = this.selectionStart;
	const end = this.selectionEnd;
	const cleaned = syj_clean_text(e.data, rule, start, Infinity);
	if (cleaned !== e.data) e.preventDefault();
});

$(document).on("paste.syj_validation", "input[data-fieldname]", function (e) {
	const rule = syj_input_rule(this);
	if (!rule) return;
	const clipboard = e.originalEvent.clipboardData || window.clipboardData;
	if (!clipboard) return;
	const start = this.selectionStart;
	const end = this.selectionEnd;
	const { max } = syj_rule_parts(rule);
	const available = max == null ? Infinity : max - ((this.value || "").length - (end - start));
	const cleaned = syj_clean_text(clipboard.getData("text"), rule, start, available);
	e.preventDefault();
	if (!cleaned) return;
	this.setRangeText(cleaned, start, end, "end");
	$(this).trigger("input").trigger("change");
});
