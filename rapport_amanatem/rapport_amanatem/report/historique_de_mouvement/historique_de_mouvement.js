// Rapport Historique de Mouvement - Amanatem
frappe.query_reports["Historique de Mouvement"] = {
	filters: [
		{
			fieldname: "item_code",
			label: __("Article"),
			fieldtype: "Link",
			options: "Item",
			reqd: 1,
		},
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
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "entree" && data.entree !== "" && data.entree != null) {
			value = `<span style="color: green; font-weight: bold;">${value}</span>`;
		}
		if (column.fieldname === "sortie" && data.sortie !== "" && data.sortie != null) {
			value = `<span style="color: red; font-weight: bold;">${value}</span>`;
		}
		return value;
	},
};
