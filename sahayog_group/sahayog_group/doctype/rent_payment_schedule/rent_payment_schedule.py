# Copyright (c) 2026, Talib Sheikh and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate, nowdate, now_datetime


class RentPaymentSchedule(Document):
	def validate(self):
		self.calculate_totals()
		self.validate_duplicate()
		self.update_invoice_status()

	def calculate_totals(self):
		total_gross = 0.0
		total_tds = 0.0
		total_gst = 0.0
		total_net = 0.0

		for row in self.landlord_schedules:
			row.gross_rent = flt(row.gross_rent)
			
			# TDS calculation (Section 7 BRD: lock 10% rate if applicable, or custom rate)
			if row.tds_applicable:
				rate = flt(row.tds_rate) or 10.0
				row.tds_rate = rate
				row.tds_amount = round(row.gross_rent * (rate / 100.0), 2)
			else:
				row.tds_amount = 0.0

			# GST calculation
			if row.gst_applicable and row.landlord_gstin:
				# Standard commercial rent GST is 18% unless invoice specified
				if flt(row.invoice_amount) and flt(row.gross_rent):
					row.gst_amount = max(0.0, flt(row.invoice_amount) - flt(row.gross_rent))
				else:
					row.gst_amount = round(row.gross_rent * 0.18, 2)
			else:
				row.gst_amount = 0.0

			row.net_payable = round(row.gross_rent + row.gst_amount - row.tds_amount, 2)

			total_gross += row.gross_rent
			total_tds += row.tds_amount
			total_gst += row.gst_amount
			total_net += row.net_payable

		self.total_gross_rent = round(total_gross, 2)
		self.total_tds = round(total_tds, 2)
		self.total_gst = round(total_gst, 2)
		self.total_net_payable = round(total_net, 2)

	def validate_duplicate(self):
		exists = frappe.db.exists("Rent Payment Schedule", {
			"compliance": self.compliance,
			"rent_month": self.rent_month,
			"rent_year": self.rent_year,
			"name": ["!=", self.name]
		})
		if exists:
			frappe.throw(_("Rent schedule for {0} {1} already exists ({2}).").format(
				self.rent_month, self.rent_year, exists
			))

	def update_invoice_status(self):
		if self.status in ("Approved", "Paid", "Rejected"):
			return
		all_uploaded = True
		for row in self.landlord_schedules:
			if row.payment_mode == "External Bank - NEFT" or row.gst_applicable:
				if not row.invoice_file:
					all_uploaded = False
		self.status = "Invoices Uploaded" if all_uploaded else "Pending Invoices"


@frappe.whitelist()
def generate_monthly_rent_schedule_for_compliance(compliance_name, month=None, year=None):
	"""Generate a single month's Rent Payment Schedule from Compliance master and Landlord Item."""
	from calendar import month_name
	today = getdate()
	month = month or month_name[today.month]
	year = int(year or today.year)

	comp = frappe.get_doc("Compliance", compliance_name)
	if not comp.is_rent:
		frappe.throw(_("{0} is not marked as Rent & Lease.").format(compliance_name))

	# Check if already exists
	existing = frappe.db.exists("Rent Payment Schedule", {
		"compliance": compliance_name,
		"rent_month": month,
		"rent_year": year
	})
	if existing:
		return frappe.get_doc("Rent Payment Schedule", existing)

	monthly_rent = flt(comp.monthly_rent)
	schedule = frappe.get_doc({
		"doctype": "Rent Payment Schedule",
		"compliance": comp.name,
		"rent_month": month,
		"rent_year": year,
		"due_date": today,
		"landlord_schedules": []
	})

	for l in comp.landlords:
		ratio = flt(l.share_ratio) or 100.0
		l_gross = round(monthly_rent * (ratio / 100.0), 2)
		schedule.append("landlord_schedules", {
			"landlord_name": l.landlord_name,
			"landlord_pan": l.landlord_pan,
			"share_ratio": ratio,
			"payment_mode": l.payment_mode,
			"sahayog_account_no": l.sahayog_account_no,
			"bank_name": l.bank_name,
			"bank_account_no": l.bank_account_no,
			"ifsc_code": l.ifsc_code,
			"gross_rent": l_gross,
			"tds_applicable": l.tds_applicable,
			"tds_rate": l.tds_rate or 10.0,
			"gst_applicable": l.gst_applicable,
			"landlord_gstin": l.landlord_gstin,
		})

	schedule.flags.ignore_permissions = True
	schedule.insert()
	return schedule


def generate_all_monthly_rent_schedules():
	"""Scheduled Cron: Auto-generate current month's rent schedule for all active rent properties."""
	from calendar import month_name
	today = getdate()
	cur_month = month_name[today.month]
	cur_year = today.year

	rent_compliances = frappe.get_all(
		"Compliance",
		filters={"is_rent": 1, "is_active": 1},
		pluck="name"
	)
	count = 0
	for c_name in rent_compliances:
		try:
			generate_monthly_rent_schedule_for_compliance(c_name, cur_month, cur_year)
			count += 1
		except Exception as e:
			frappe.logger("rent_schedule").error(f"Failed to generate rent schedule for {c_name}: {e}")
	return count


def apply_auto_rent_increments():
	"""
	Scheduled Cron (BRD Sec 9):
	Revised monthly rent = Existing monthly rent * (1 + Increment percentage / 100)
	Triggers when next_increment_date <= today.
	"""
	from frappe.utils import add_months
	today = getdate(nowdate())

	compliances = frappe.get_all(
		"Compliance",
		filters={
			"is_rent": 1,
			"is_active": 1,
			"next_increment_date": ["<=", today],
			"increment_percentage": [">", 0]
		},
		fields=["name", "compliance_name", "monthly_rent", "increment_percentage", "increment_frequency", "next_increment_date"]
	)

	freq_map = {
		"Every 11 Months": 11,
		"Annual": 12,
		"Every 2 Years": 24,
		"Every 3 Years": 36,
	}

	for c in compliances:
		doc = frappe.get_doc("Compliance", c.name)
		old_rent = flt(doc.monthly_rent)
		inc_pct = flt(doc.increment_percentage)
		
		# Revised rent formula as per BRD
		new_rent = round(old_rent * (1.0 + (inc_pct / 100.0)), 2)
		doc.monthly_rent = new_rent
		
		# Compute next increment date
		months_to_add = freq_map.get(doc.increment_frequency, 12)
		doc.next_increment_date = add_months(getdate(doc.next_increment_date), months_to_add)

		doc.flags.ignore_permissions = True
		doc.save()

		doc.add_comment(
			"Comment",
			f"Automatic Rent Escalation Applied: Monthly Rent revised from ₹{old_rent} to ₹{new_rent} (+{inc_pct}%). Next Increment Date: {doc.next_increment_date}"
		)
		frappe.logger("rent_increment").info(f"Escalation applied for {doc.name}: {old_rent} -> {new_rent}")
