import re

import frappe
from frappe import _

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
GSTIN_RE = re.compile(r"^[A-Z0-9]{15}$")
ALNUM_RE = re.compile(r"^[\w\s.,/\-&'()]+$", re.UNICODE)

LANDLORD_FIELDS = {
	"landlord_name": "letters",
	"landlord_pan": "pan",
	"bank_name": "letters",
	"sahayog_account_no": "digits:15",
	"bank_account_no": "digits",
	"ifsc_code": "ifsc",
	"landlord_gstin": "gstin",
}

DOCTYPE_FIELDS = {
	"Compliance": {
		"compliance_name": "letters",
		"issuing_authority": "letters",
		"sol_id": "digits",
		"branch_name": "letters",
	},
	"Compliance Category": {"category": "letters"},
	"Compliance Company": {"company": "letters"},
	"Compliance Department": {"department": "letters"},
	"Compliance Project": {"project": "letters", "place": "letters"},
	"Evidence Type": {"type_name": "letters"},
	"Compliance Landlord Item": LANDLORD_FIELDS,
	"Rent Schedule Item": LANDLORD_FIELDS,
	"Rent Payment Schedule": {"sol_id": "digits", "branch_name": "letters"},
	"Compliance Request": {"application_reference_no": "alphanumeric"},
	"Evidence Item": {"period": "alphanumeric", "arn__reference_no": "alphanumeric"},
	"Evidence File Version": {"period": "alphanumeric"},
}

CHILD_TABLE_FIELDS = {
	"landlords": "Compliance Landlord Item",
	"landlord_schedules": "Rent Schedule Item",
}


def _label(doc, fieldname):
	try:
		return doc.meta.get_label(fieldname) or fieldname
	except Exception:
		return fieldname


def _throw(label, message):
	frappe.throw(
		_("{0}: {1}").format(frappe.bold(_(label)), message),
		title=_("Invalid Field Value"),
	)


def _letters(value, label, arg=None):
	value = str(value or "").strip()
	if any(char.isdigit() for char in value):
		_throw(label, _("Numbers are not allowed. Use letters only."))
	return value


def _digits(value, label, arg=None):
	value = re.sub(r"[\s-]", "", str(value or ""))
	if value and not (value.isascii() and value.isdigit()):
		_throw(label, _("Only digits are allowed. Letters and symbols are not allowed."))
	if arg and len(value) != int(arg):
		_throw(label, _("Must be exactly {0} digits.").format(arg))
	return value


def _alphanumeric(value, label, arg=None):
	value = str(value or "").strip()
	if value and not ALNUM_RE.match(value):
		_throw(
			label,
			_("Only letters, digits, spaces and . , / - & ' ( ) are allowed."),
		)
	return value


def _pan(value, label, arg=None):
	value = str(value or "").strip().upper()
	if value and not PAN_RE.match(value):
		_throw(
			label,
			_("PAN must be 10 characters: 5 letters, 4 digits, 1 letter (for example ABCDE1234F)."),
		)
	return value


def _ifsc(value, label, arg=None):
	value = str(value or "").strip().upper()
	if value and not IFSC_RE.match(value):
		_throw(
			label,
			_("IFSC must be 11 characters: 4 letters, 0, then 6 letters or digits (for example SBIN0001234)."),
		)
	return value


def _gstin(value, label, arg=None):
	value = str(value or "").strip().upper()
	if value and not GSTIN_RE.match(value):
		_throw(label, _("GSTIN must be 15 letters or digits."))
	return value


VALIDATORS = {
	"letters": _letters,
	"digits": _digits,
	"alphanumeric": _alphanumeric,
	"pan": _pan,
	"ifsc": _ifsc,
	"gstin": _gstin,
}


def validate_fields(doc, fields, row_label=""):
	for fieldname, rule in fields.items():
		if doc.get(fieldname) in (None, ""):
			continue
		name, _, arg = rule.partition(":")
		validator = VALIDATORS.get(name)
		if not validator:
			continue
		label = "{0}{1}".format(row_label, _label(doc, fieldname))
		doc.set(fieldname, validator(doc.get(fieldname), label, arg))


def validate_doc(doc):
	"""Validate every Sahayog doctype (and its child rows) before saving."""
	rules = DOCTYPE_FIELDS.get(doc.doctype)
	if rules:
		validate_fields(doc, rules)

	for table_fieldname, child_doctype in CHILD_TABLE_FIELDS.items():
		child_rules = DOCTYPE_FIELDS.get(child_doctype)
		if not child_rules:
			continue
		for index, row in enumerate(doc.get(table_fieldname) or [], 1):
			validate_fields(row, child_rules, _("Row {0}: ").format(index))
