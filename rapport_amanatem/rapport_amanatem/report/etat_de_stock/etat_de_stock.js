// Rapport Etat de Stock - Amanatem
frappe.query_reports["Etat de Stock"] = {
	filters: [
		{
			fieldname: "date_debut",
			label: __("Date Début"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.year_start(),
		},
		{
			fieldname: "date_fin",
			label: __("Date Fin"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
		{
			fieldname: "warehouse",
			label: __("Dépôt"),
			fieldtype: "Link",
			options: "Warehouse",
		},
	],
};
