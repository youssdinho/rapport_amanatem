"""
Rapport Historique de Mouvement - Amanatem
Affiche le stock de départ puis tous les mouvements d'un article sur une période.
Le prix affiché est le prix HT du document source (pas le coût de revient).
"""
import frappe
from frappe import _
from frappe.utils import getdate

VOUCHER_LABELS = {
	"Purchase Receipt": "Bon de Réception",
	"Purchase Invoice": "Facture Achat",
	"Sales Invoice": "Facture Vente",
	"Delivery Note": "Bon de Livraison",
	"Stock Entry": "Ecriture de Stock",
	"Stock Reconciliation": "Réconciliation Stock",
	"Purchase Return": "Retour Achat",
}

# Table des lignes par type de document → (table_enfant, champ_parent, champ_prix)
VOUCHER_ITEM_TABLE = {
	"Purchase Receipt":     ("tabPurchase Receipt Item",     "parent", "net_rate"),
	"Purchase Invoice":     ("tabPurchase Invoice Item",     "parent", "net_rate"),
	"Sales Invoice":        ("tabSales Invoice Item",        "parent", "net_rate"),
	"Delivery Note":        ("tabDelivery Note Item",        "parent", "net_rate"),
	"Stock Entry":          ("tabStock Entry Detail",        "parent", "basic_rate"),
	"Stock Reconciliation": ("tabStock Reconciliation Item", "parent", "valuation_rate"),
}


def execute(filters=None):
	filters = filters or {}
	validate_filters(filters)
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def validate_filters(filters):
	if not filters.get("item_code"):
		frappe.throw(_("Veuillez sélectionner un Article"))
	if not filters.get("date_debut"):
		frappe.throw(_("Veuillez sélectionner une Date Début"))
	if not filters.get("date_fin"):
		frappe.throw(_("Veuillez sélectionner une Date Fin"))
	if getdate(filters["date_debut"]) > getdate(filters["date_fin"]):
		frappe.throw(_("La Date Début ne peut pas être supérieure à la Date Fin"))


def get_columns():
	return [
		{
			"fieldname": "date",
			"label": _("Date"),
			"fieldtype": "Date",
			"width": 110,
		},
		{
			"fieldname": "type_mouvement",
			"label": _("Type"),
			"fieldtype": "Data",
			"width": 180,
		},
		{
			"fieldname": "voucher_no",
			"label": _("N° Document"),
			"fieldtype": "Dynamic Link",
			"options": "voucher_type",
			"width": 180,
		},
		{
			"fieldname": "warehouse",
			"label": _("Dépôt"),
			"fieldtype": "Link",
			"options": "Warehouse",
			"width": 160,
		},
		{
			"fieldname": "entree",
			"label": _("Entrée"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 110,
		},
		{
			"fieldname": "sortie",
			"label": _("Sortie"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 110,
		},
		{
			"fieldname": "prix_unitaire",
			"label": _("Prix Unitaire HT"),
			"fieldtype": "Currency",
			"width": 140,
		},
		{
			"fieldname": "stock_apres",
			"label": _("Stock Après"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 120,
		},
	]


def get_prix_map(mouvements, item_code):
	"""
	Construit un dict (voucher_type, voucher_no) -> prix HT
	en allant chercher le prix dans la table enfant de chaque document.
	"""
	# Regrouper les vouchers par type
	by_type = {}
	for m in mouvements:
		by_type.setdefault(m.voucher_type, set()).add(m.voucher_no)

	prix_map = {}
	for voucher_type, voucher_nos in by_type.items():
		mapping = VOUCHER_ITEM_TABLE.get(voucher_type)
		if not mapping:
			continue
		table, parent_field, rate_field = mapping
		if not voucher_nos:
			continue

		placeholders = ", ".join(["%s"] * len(voucher_nos))
		rows = frappe.db.sql(
			f"""
			SELECT `{parent_field}` AS voucher_no, `{rate_field}` AS rate
			FROM `{table}`
			WHERE `{parent_field}` IN ({placeholders})
				AND item_code = %s
			""",
			list(voucher_nos) + [item_code],
			as_dict=True,
		)
		for r in rows:
			prix_map[(voucher_type, r.voucher_no)] = r.rate or 0.0

	return prix_map


def get_data(filters):
	warehouse_condition = ""
	if filters.get("warehouse"):
		warehouse_condition = "AND sle.warehouse = %(warehouse)s"

	params = {
		"item_code": filters["item_code"],
		"date_debut": filters["date_debut"],
		"date_fin": filters["date_fin"],
		"warehouse": filters.get("warehouse"),
	}

	# Stock de départ = cumul de tous les mouvements avant date_debut
	stock_depart_data = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(sle.actual_qty), 0) AS stock_depart
		FROM `tabStock Ledger Entry` sle
		WHERE sle.docstatus = 1
			AND sle.is_cancelled = 0
			AND sle.item_code = %(item_code)s
			AND sle.posting_date < %(date_debut)s
			{warehouse_condition}
		""",
		params,
		as_dict=True,
	)
	stock_depart = stock_depart_data[0].stock_depart if stock_depart_data else 0.0

	# Tous les mouvements dans la période
	mouvements = frappe.db.sql(
		f"""
		SELECT
			sle.posting_date          AS date,
			sle.voucher_type,
			sle.voucher_no,
			sle.warehouse,
			sle.actual_qty,
			sle.qty_after_transaction AS stock_apres
		FROM `tabStock Ledger Entry` sle
		WHERE sle.docstatus = 1
			AND sle.is_cancelled = 0
			AND sle.item_code = %(item_code)s
			AND sle.posting_date >= %(date_debut)s
			AND sle.posting_date <= %(date_fin)s
			{warehouse_condition}
		ORDER BY sle.posting_date, sle.posting_time, sle.creation
		""",
		params,
		as_dict=True,
	)

	# Récupérer les prix HT depuis les documents sources
	prix_map = get_prix_map(mouvements, filters["item_code"])

	rows = []

	# Ligne stock de départ
	rows.append({
		"date": filters["date_debut"],
		"type_mouvement": _("--- Stock de Départ ---"),
		"voucher_no": "",
		"voucher_type": "",
		"warehouse": filters.get("warehouse") or "",
		"entree": stock_depart,
		"sortie": "",
		"prix_unitaire": "",
		"stock_apres": stock_depart,
	})

	# Lignes de mouvements
	for m in mouvements:
		entree = m.actual_qty if m.actual_qty > 0 else 0.0
		sortie = abs(m.actual_qty) if m.actual_qty < 0 else 0.0
		label = VOUCHER_LABELS.get(m.voucher_type, m.voucher_type)
		prix = prix_map.get((m.voucher_type, m.voucher_no), 0.0)

		rows.append({
			"date": m.date,
			"type_mouvement": label,
			"voucher_no": m.voucher_no,
			"voucher_type": m.voucher_type,
			"warehouse": m.warehouse,
			"entree": entree or "",
			"sortie": sortie or "",
			"prix_unitaire": prix,
			"stock_apres": m.stock_apres,
		})

	return rows
