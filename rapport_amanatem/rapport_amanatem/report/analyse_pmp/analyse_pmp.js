// Rapport Analyse PMP - Amanatem
// Compare le PMP ERPNext avec notre propre calcul du PMP (tous les prix HT)
frappe.query_reports["Analyse PMP"] = {
	filters: [
		{
			fieldname: "date_debut",
			label: __("Date Début"),
			fieldtype: "Date",
			reqd: 1,
			default: "2026-01-01",
		},
		{
			fieldname: "date_fin",
			label: __("Date Fin"),
			fieldtype: "Date",
			reqd: 1,
			default: frappe.datetime.get_today(),
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "ecart" && data) {
			const ecart = parseFloat(data.ecart) || 0;
			if (Math.abs(ecart) < 0.01) {
				value = `<span style="color: green; font-weight: bold;">${value}</span>`;
			} else {
				value = `<span style="color: red; font-weight: bold;">${value}</span>`;
			}
		}
		return value;
	},
};
