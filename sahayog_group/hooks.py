app_name = "sahayog_group"
app_title = "Compliance"
app_publisher = "Talib Sheikh"
app_description = "Sahayog Group"
app_email = "talibsheikh16@gmail.com"
app_license = "mit"

# Apps
# ------------------

add_to_apps_screen = [
	{
		"name": "sahayog_group",
		"logo": "/assets/sahayog_group/icons/organization.svg",
		"title": "Compliance",
		"route": "/desk/compliance-management",
	}
]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/sahayog_group/css/sahayog_group.css"
# app_include_js = "/assets/sahayog_group/js/sahayog_group.js"

# include js, css files in header of web template
# web_include_css = "/assets/sahayog_group/css/sahayog_group.css"
# web_include_js = "/assets/sahayog_group/js/sahayog_group.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "sahayog_group/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
# doctype_js = {"doctype" : "public/js/doctype.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "sahayog_group/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# automatically load and sync documents of this doctype from downstream apps
# importable_doctypes = [doctype_1]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "sahayog_group.utils.jinja_methods",
# 	"filters": "sahayog_group.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "sahayog_group.install.before_install"
# after_install = "sahayog_group.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "sahayog_group.uninstall.before_uninstall"
# after_uninstall = "sahayog_group.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "sahayog_group.utils.before_app_install"
# after_app_install = "sahayog_group.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "sahayog_group.utils.before_app_uninstall"
# after_app_uninstall = "sahayog_group.utils.after_app_uninstall"

# Build
# ------------------
# To hook into the build process

# after_build = "sahayog_group.build.after_build"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "sahayog_group.notifications.get_notification_config"

# Awesome Bar
# -----------
# Extra search results: list of dicts with label, description, route, index.
# route: ["List", "ToDo"], "/desk/docs/some/page", or "https://example.com"
# awesomebar_search = ["sahayog_group.search.awesomebar_results"]

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# Document Events
# ---------------
# Hook on document methods and events

# doc_events = {
# 	"*": {
# 		"on_update": "method",
# 		"on_cancel": "method",
# 		"on_trash": "method"
# 	}
# }

# Scheduled Tasks
# ---------------

scheduler_events = {
	"daily": [
		"sahayog_group.sahayog_group.doctype.compliance.compliance.check_and_create_all_compliance_requests",
		"sahayog_group.sahayog_group.doctype.compliance_request.compliance_request.check_and_set_overdue",
		"sahayog_group.sahayog_group.doctype.compliance_request.compliance_request.send_compliance_alerts",
		"sahayog_group.sahayog_group.doctype.compliance_request.compliance_request.escalate_unacknowledged_alerts",
		"sahayog_group.sahayog_group.doctype.rent_payment_schedule.rent_payment_schedule.apply_auto_rent_increments",
	],
	"monthly": [
		"sahayog_group.sahayog_group.doctype.rent_payment_schedule.rent_payment_schedule.generate_all_monthly_rent_schedules",
	],
}
# old_scheduler = {
# 	"all": [
# 		"sahayog_group.tasks.all"
# 	],
# 	"daily": [
# 		"sahayog_group.tasks.daily"
# 	],
# 	"hourly": [
# 		"sahayog_group.tasks.hourly"
# 	],
# 	"weekly": [
# 		"sahayog_group.tasks.weekly"
# 	],
# 	"monthly": [
# 		"sahayog_group.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "sahayog_group.install.before_tests"

# Extend DocType Class
# ------------------------------
#
# Specify custom mixins to extend the standard doctype controller.
# extend_doctype_class = {
# 	"Task": "sahayog_group.custom.task.CustomTaskMixin"
# }

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "sahayog_group.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "sahayog_group.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["sahayog_group.utils.before_request"]
# after_request = ["sahayog_group.utils.after_request"]

# Job Events
# ----------
# before_job = ["sahayog_group.utils.before_job"]
# after_job = ["sahayog_group.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"sahayog_group.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

# Translation
# ------------
# List of apps whose translatable strings should be excluded from this app's translations.
# ignore_translatable_strings_from = []


# ---- Compliance: roles, scope and permissions ----
permission_query_conditions = {
	"Compliance Request": "sahayog_group.sahayog_group.permissions.request_conditions",
	"Compliance": "sahayog_group.sahayog_group.permissions.compliance_conditions",
	"Alert Log": "sahayog_group.sahayog_group.permissions.alert_log_conditions",
	"Compliance Project": "sahayog_group.sahayog_group.permissions.project_conditions",
	"Compliance Audit Log": "sahayog_group.sahayog_group.permissions.audit_log_conditions",
	"Evidence File Version": "sahayog_group.sahayog_group.permissions.version_conditions",
}

has_permission = {
	"Compliance Request": "sahayog_group.sahayog_group.permissions.has_permission",
	"Compliance": "sahayog_group.sahayog_group.permissions.has_permission",
	"Compliance Project": "sahayog_group.sahayog_group.permissions.project_has_permission",
	"Compliance Audit Log": "sahayog_group.sahayog_group.permissions.linked_has_permission",
	"Evidence File Version": "sahayog_group.sahayog_group.permissions.linked_has_permission",
}

doc_events = {
	"Compliance": {"on_update": "sahayog_group.sahayog_group.roles.sync_roles_for_doc"},
	"Compliance Department": {"on_update": "sahayog_group.sahayog_group.roles.sync_roles_for_doc"},
	"Compliance Project": {"on_update": "sahayog_group.sahayog_group.roles.sync_roles_for_doc"},
	"Compliance Request": {
		"validate": "sahayog_group.sahayog_group.audit_controls.request_validate",
		"on_update": "sahayog_group.sahayog_group.audit_controls.request_on_update",
	},
}

doctype_js = {
	"Compliance Request": "public/js/compliance_request_brd.js",
	"User": "public/js/user_compliance_reassign.js",
}

doctype_list_js = {
	"Compliance": "public/js/compliance_list_custom.js",
}

after_migrate = ["sahayog_group.sahayog_group.roles.setup_roles"]
