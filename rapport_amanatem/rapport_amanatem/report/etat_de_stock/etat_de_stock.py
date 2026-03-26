"""
Rapport Etat de Stock - Amanatem
Colonnes : Stock Initial, Entrée, Sortie, Restant, Stock ERPNext, Ecart
Stock Initial = stock avant la date de début choisie
"""
import frappe
from frappe import _
from frappe.utils import getdate


def execute(filters=None):
	filters = filters or {}
	validate_filters(filters)
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def validate_filters(filters):
	if not filters.get("date_debut"):
		frappe.throw(_("Veuillez sélectionner une Date Début"))
	if not filters.get("date_fin"):
		frappe.throw(_("Veuillez sélectionner une Date Fin"))
	if getdate(filters["date_debut"]) > getdate(filters["date_fin"]):
		frappe.throw(_("La Date Début ne peut pas être supérieure à la Date Fin"))


def get_columns():
	return [
		{
			"fieldname": "item_code",
			"label": _("Code Article"),
			"fieldtype": "Link",
			"options": "Item",
			"width": 180,
		},
		{
			"fieldname": "item_name",
			"label": _("Désignation"),
			"fieldtype": "Data",
			"width": 280,
		},
		{
			"fieldname": "stock_initial",
			"label": _("Stock Initial"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"fieldname": "entree",
			"label": _("Entrée"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"fieldname": "sortie",
			"label": _("Sortie"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"fieldname": "restant",
			"label": _("Restant"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"fieldname": "stock_erpnext",
			"label": _("Stock ERPNext"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 130,
		},
		{
			"fieldname": "ecart",
			"label": _("Ecart"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 110,
		},
	]


def get_data(filters):
	warehouse_condition = ""
	if filters.get("warehouse"):
		warehouse_condition = "AND sle.warehouse = %(warehouse)s"

	params = {
		"date_debut": filters["date_debut"],
		"date_fin": filters["date_fin"],
		"warehouse": filters.get("warehouse"),
	}

	# Stock initial = tout ce qui s'est passé AVANT la date de début (hors annulés)
	stock_initial_data = frappe.db.sql(
		f"""
		SELECT
			sle.item_code,
			SUM(sle.actual_qty) AS stock_initial
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabItem` i ON i.name = sle.item_code
		WHERE sle.docstatus = 1
			AND sle.is_cancelled = 0
			AND i.disabled = 0
			AND sle.posting_date < %(date_debut)s
			{warehouse_condition}
		GROUP BY sle.item_code
		""",
		params,
		as_dict=True,
	)

	# Mouvements dans la période : entrées (+) et sorties (-) (hors annulés)
	mouvements_data = frappe.db.sql(
		f"""
		SELECT
			sle.item_code,
			SUM(CASE WHEN sle.actual_qty > 0 THEN sle.actual_qty ELSE 0 END) AS entree,
			SUM(CASE WHEN sle.actual_qty < 0 THEN ABS(sle.actual_qty) ELSE 0 END) AS sortie
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabItem` i ON i.name = sle.item_code
		WHERE sle.docstatus = 1
			AND sle.is_cancelled = 0
			AND i.disabled = 0
			AND sle.posting_date >= %(date_debut)s
			AND sle.posting_date <= %(date_fin)s
			{warehouse_condition}
		GROUP BY sle.item_code
		""",
		params,
		as_dict=True,
	)

	# Tous les articles ayant eu un mouvement valide (hors annulés)
	all_items = frappe.db.sql(
		"""
		SELECT DISTINCT
			sle.item_code,
			i.item_name
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabItem` i ON i.name = sle.item_code
		WHERE sle.docstatus = 1
			AND sle.is_cancelled = 0
			AND i.disabled = 0
		ORDER BY sle.item_code
		""",
		as_dict=True,
	)

	# Stock actuel ERPNext depuis tabBin (stock réel affiché par ERPNext)
	bin_warehouse_condition = ""
	if filters.get("warehouse"):
		bin_warehouse_condition = "AND b.warehouse = %(warehouse)s"

	bin_data = frappe.db.sql(
		f"""
		SELECT
			b.item_code,
			SUM(b.actual_qty) AS stock_erpnext
		FROM `tabBin` b
		INNER JOIN `tabItem` i ON i.name = b.item_code
		WHERE i.disabled = 0
			{bin_warehouse_condition}
		GROUP BY b.item_code
		""",
		params,
		as_dict=True,
	)

	initial_map = {r.item_code: r.stock_initial or 0.0 for r in stock_initial_data}
	mouv_map = {r.item_code: r for r in mouvements_data}
	bin_map = {r.item_code: r.stock_erpnext or 0.0 for r in bin_data}

	rows = []
	for item in all_items:
		code = item.item_code
		stock_initial = initial_map.get(code, 0.0)
		m = mouv_map.get(code)
		entree = m.entree if m else 0.0
		sortie = m.sortie if m else 0.0
		restant = stock_initial + entree - sortie
		stock_erpnext = bin_map.get(code, 0.0)
		ecart = restant - stock_erpnext

		if stock_initial == 0 and entree == 0 and sortie == 0 and stock_erpnext == 0:
			continue

		rows.append({
			"item_code": code,
			"item_name": item.item_name,
			"stock_initial": stock_initial,
			"entree": entree,
			"sortie": sortie,
			"restant": restant,
			"stock_erpnext": stock_erpnext,
			"ecart": ecart,
		})

	return rows
