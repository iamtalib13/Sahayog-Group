import re

import frappe
from frappe import _
from frappe.utils import flt

PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
IFSC_RE = re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$")
SAHAYOG = "Sahayog Savings Account"
NEFT = "External Bank - NEFT"


def _pct(value):
    return ("%.2f" % value).rstrip("0").rstrip(".")


def validate_landlords(doc):
    """Rent details: at least one landlord, shares add up to at most 100%, PAN format and payment-mode details."""
    rows = doc.get("landlords") or []
    errors = []

    if doc.get("is_rent") and not rows:
        frappe.throw(_("Add at least one Landlord in the Rent Details tab."), title=_("Landlords"))

    remaining = 100.0
    for row in rows:
        n = row.idx
        who = _("Landlord {0}").format(n)

        # ---- share ratio
        share = round(flt(row.share_ratio), 2)
        if share <= 0:
            errors.append(_("{0}: Share Ratio must be greater than 0.").format(who))
        elif share > round(remaining, 2):
            errors.append(
                _("{0}: Share Ratio {1}% is more than the remaining {2}%.").format(who, _pct(share), _pct(remaining))
            )
        else:
            remaining = round(remaining - share, 2)

        # ---- PAN
        pan = (row.landlord_pan or "").strip().upper()
        row.landlord_pan = pan
        if pan and not PAN_RE.match(pan):
            errors.append(
                _("{0}: Landlord PAN is not valid. It must be 10 characters: 5 letters, 4 digits, 1 letter (for example ABCDE1234F).").format(who)
            )

        # ---- payment mode details
        mode = row.payment_mode
        if mode == SAHAYOG:
            acc = (row.sahayog_account_no or "").strip()
            row.sahayog_account_no = acc
            if not acc:
                errors.append(_("{0}: Sahayog Savings A/c No is mandatory.").format(who))
            elif not (acc.isascii() and acc.isdigit()):
                errors.append(_("{0}: Sahayog Savings A/c No must contain digits only.").format(who))
            elif len(acc) != 15:
                errors.append(
                    _("{0}: Sahayog Savings A/c No must be exactly 15 digits (you entered {1}).").format(who, len(acc))
                )
        elif mode == NEFT:
            bank = (row.bank_name or "").strip()
            acc = (row.bank_account_no or "").strip()
            ifsc = (row.ifsc_code or "").strip().upper()
            row.bank_name, row.bank_account_no, row.ifsc_code = bank, acc, ifsc
            if not bank:
                errors.append(_("{0}: Bank Name is mandatory.").format(who))
            if not acc:
                errors.append(_("{0}: Bank Account No is mandatory.").format(who))
            if not ifsc:
                errors.append(_("{0}: IFSC Code is mandatory.").format(who))
            elif not IFSC_RE.match(ifsc):
                errors.append(
                    _("{0}: IFSC Code must be 11 characters: 4 letters, then 0, then 6 letters or digits (for example SBIN0001234).").format(who)
                )

    if errors:
        frappe.throw("<ul>" + "".join("<li>%s</li>" % e for e in errors) + "</ul>", title=_("Landlord Details"))
