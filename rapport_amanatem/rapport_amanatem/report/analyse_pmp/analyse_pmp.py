"""
Rapport Analyse PMP - Amanatem
==============================
Compare le PMP calculé par ERPNext avec notre propre calcul du PMP.

Méthode de calcul : FIFO (identique à ERPNext)
- Stock initial       : file FIFO (stock_queue) du dernier SLE AVANT la date de début
- Entrée achat        : ajout d'une couche [qty, prix_HT] en fin de file
- Retour client       : ajout d'une couche [qty, pmp_courant] en fin de file
- Sortie / retour fo  : consommation des couches les plus anciennes (FIFO)
- PMP affiché         : moyenne pondérée des couches restantes

Sources de prix HT (depuis les documents) :
  Purchase Receipt  → tabPurchase Receipt Item.net_rate
  Purchase Invoice  → tabPurchase Invoice Item.net_rate
  Stock Entry       → tabStock Entry Detail.basic_rate

Tous les prix affichés sont HT.
"""
import json
import frappe
from frappe import _
from frappe.utils import getdate


IS_RETURN_DOCTYPES = {"Sales Invoice", "Delivery Note", "Purchase Receipt", "Purchase Invoice"}

PRIX_DETAIL_MAP = {
	"Purchase Receipt": ("tabPurchase Receipt Item", "net_rate"),
	"Purchase Invoice": ("tabPurchase Invoice Item", "net_rate"),
	"Stock Entry":      ("tabStock Entry Detail",    "basic_rate"),
}


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
			"width": 160,
		},
		{
			"fieldname": "item_name",
			"label": _("Désignation"),
			"fieldtype": "Data",
			"width": 300,
		},
		{
			"fieldname": "qty_stock",
			"label": _("Qté en Stock"),
			"fieldtype": "Float",
			"precision": 3,
			"width": 120,
		},
		{
			"fieldname": "pmp_erpnext",
			"label": _("PMP ERPNext HT"),
			"fieldtype": "Currency",
			"width": 160,
		},
		{
			"fieldname": "pmp_calcule",
			"label": _("PMP Calculé HT"),
			"fieldtype": "Currency",
			"width": 160,
		},
		{
			"fieldname": "ecart",
			"label": _("Écart HT"),
			"fieldtype": "Currency",
			"width": 130,
		},
	]


# ---------------------------------------------------------------------------
# Helpers FIFO
# ---------------------------------------------------------------------------

def queue_pmp(queue):
	"""Moyenne pondérée des couches FIFO restantes."""
	total_qty = sum(layer[0] for layer in queue)
	if total_qty <= 0:
		return 0.0
	return sum(layer[0] * layer[1] for layer in queue) / total_qty


def fifo_consume(queue, qty_to_consume):
	"""Consomme qty_to_consume depuis le début de la file FIFO."""
	remaining = qty_to_consume
	new_queue = []
	for layer_qty, layer_rate in queue:
		if remaining <= 0:
			new_queue.append([layer_qty, layer_rate])
		elif remaining >= layer_qty:
			remaining -= layer_qty
		else:
			new_queue.append([layer_qty - remaining, layer_rate])
			remaining = 0.0
	return new_queue


# ---------------------------------------------------------------------------
# Données de base
# ---------------------------------------------------------------------------

def get_opening_state(date_debut):
	"""
	Retourne la file FIFO (stock_queue) du dernier SLE AVANT date_debut.
	Si stock_queue est vide mais qu'il y a du stock, crée une couche unique.
	"""
	rows = frappe.db.sql(
		"""
		SELECT
			sle.item_code,
			sle.qty_after_transaction AS qty,
			sle.valuation_rate        AS pmp,
			sle.stock_queue
		FROM `tabStock Ledger Entry` sle
		INNER JOIN (
			SELECT item_code, MAX(posting_datetime) AS max_dt
			FROM `tabStock Ledger Entry`
			WHERE posting_date < %(date_debut)s
				AND docstatus = 1
				AND is_cancelled = 0
			GROUP BY item_code
		) last_sle
			ON  last_sle.item_code = sle.item_code
			AND last_sle.max_dt    = sle.posting_datetime
		WHERE sle.posting_date < %(date_debut)s
			AND sle.docstatus = 1
			AND sle.is_cancelled = 0
		""",
		{"date_debut": date_debut},
		as_dict=True,
	)
	opening = {}
	for r in rows:
		qty = r.qty or 0.0
		pmp = r.pmp or 0.0
		try:
			queue = json.loads(r.stock_queue or "[]")
		except (ValueError, TypeError):
			queue = []
		if not queue and qty > 0 and pmp > 0:
			queue = [[qty, pmp]]
		opening[r.item_code] = {"queue": queue}
	return opening


def get_mouvements(date_debut, date_fin):
	"""Tous les SLE dans la période, triés par article puis datetime."""
	return frappe.db.sql(
		"""
		SELECT
			sle.item_code,
			sle.posting_datetime,
			sle.actual_qty,
			sle.incoming_rate,
			sle.voucher_type,
			sle.voucher_no,
			sle.voucher_detail_no
		FROM `tabStock Ledger Entry` sle
		INNER JOIN `tabItem` i ON i.name = sle.item_code
		WHERE sle.docstatus = 1
			AND sle.is_cancelled = 0
			AND i.disabled = 0
			AND sle.posting_date >= %(date_debut)s
			AND sle.posting_date <= %(date_fin)s
		ORDER BY sle.item_code, sle.posting_datetime, sle.creation
		""",
		{"date_debut": date_debut, "date_fin": date_fin},
		as_dict=True,
	)


def get_is_return_map(mouvements):
	by_type = {}
	for m in mouvements:
		if m.actual_qty > 0 and m.voucher_type in IS_RETURN_DOCTYPES:
			by_type.setdefault(m.voucher_type, set()).add(m.voucher_no)

	is_return_map = {}
	for voucher_type, voucher_nos in by_type.items():
		if not voucher_nos:
			continue
		table = "tab" + voucher_type
		placeholders = ", ".join(["%s"] * len(voucher_nos))
		rows = frappe.db.sql(
			f"SELECT name, is_return FROM `{table}` WHERE name IN ({placeholders})",
			list(voucher_nos),
			as_dict=True,
		)
		for r in rows:
			is_return_map[(voucher_type, r.name)] = bool(r.is_return)

	return is_return_map


def get_prix_achat_map(mouvements, is_return_map):
	by_type = {}
	for m in mouvements:
		if m.actual_qty <= 0:
			continue
		if is_return_map.get((m.voucher_type, m.voucher_no), False):
			continue
		if m.voucher_type not in PRIX_DETAIL_MAP:
			continue
		if not m.voucher_detail_no:
			continue
		by_type.setdefault(m.voucher_type, set()).add(m.voucher_detail_no)

	prix_map = {}
	for voucher_type, detail_nos in by_type.items():
		detail_nos = list(filter(None, detail_nos))
		if not detail_nos:
			continue
		table, rate_field = PRIX_DETAIL_MAP[voucher_type]
		placeholders = ", ".join(["%s"] * len(detail_nos))
		rows = frappe.db.sql(
			f"SELECT name, `{rate_field}` AS rate FROM `{table}` WHERE name IN ({placeholders})",
			detail_nos,
			as_dict=True,
		)
		for r in rows:
			prix_map[r.name] = r.rate or 0.0

	return prix_map


def get_bin_data():
	rows = frappe.db.sql(
		"""
		SELECT
			b.item_code,
			SUM(b.actual_qty) AS qty,
			SUM(b.actual_qty * b.valuation_rate) / NULLIF(SUM(b.actual_qty), 0) AS pmp_erpnext
		FROM `tabBin` b
		INNER JOIN `tabItem` i ON i.name = b.item_code
		WHERE i.disabled = 0
		GROUP BY b.item_code
		HAVING qty > 0
		""",
		as_dict=True,
	)
	return {r.item_code: r for r in rows}


# ---------------------------------------------------------------------------
# Calcul du PMP en FIFO
# ---------------------------------------------------------------------------

def calculate_pmp(opening, mouvements, is_return_map, prix_map):
	"""
	Calcule le PMP FIFO pour chaque article en traitant les mouvements
	chronologiquement, identique à la méthode ERPNext.

	- Entrée achat      : ajoute [qty, prix_HT] en fin de file
	- Retour client     : ajoute [qty, pmp_courant] en fin de file
	- Sortie / retour fo: consomme les couches les plus anciennes (FIFO)
	"""
	state = {code: {"queue": list(o["queue"])} for code, o in opening.items()}

	for m in mouvements:
		code = m.item_code
		if code not in state:
			state[code] = {"queue": []}

		s = state[code]
		qty = m.actual_qty

		if qty > 0:
			key = (m.voucher_type, m.voucher_no)
			if is_return_map.get(key, False):
				# Retour client : valorisé au PMP courant de la file
				rate = queue_pmp(s["queue"])
			else:
				# Achat : prix HT depuis le document source
				rate = prix_map.get(m.voucher_detail_no or "", 0.0)
				if not rate:
					rate = m.incoming_rate or 0.0
			s["queue"].append([qty, rate])

		elif qty < 0:
			# Sortie : consommation FIFO depuis le début de la file
			s["queue"] = fifo_consume(s["queue"], abs(qty))

	return {code: {"pmp": queue_pmp(s["queue"])} for code, s in state.items()}


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def get_data(filters):
	date_debut = filters["date_debut"]
	date_fin   = filters["date_fin"]

	opening       = get_opening_state(date_debut)
	mouvements    = get_mouvements(date_debut, date_fin)
	is_return_map = get_is_return_map(mouvements)
	prix_map      = get_prix_achat_map(mouvements, is_return_map)
	pmp_state     = calculate_pmp(opening, mouvements, is_return_map, prix_map)
	bin_data      = get_bin_data()

	item_name_map = {
		r.name: r.item_name
		for r in frappe.db.sql(
			"SELECT name, item_name FROM `tabItem` WHERE disabled = 0",
			as_dict=True,
		)
	}

	rows = []
	for item_code, b in bin_data.items():
		qty_stock   = b.qty or 0.0
		pmp_erpnext = b.pmp_erpnext or 0.0
		pmp_calcule = pmp_state.get(item_code, {}).get("pmp", 0.0)
		ecart       = round(pmp_erpnext - pmp_calcule, 6)

		rows.append({
			"item_code":   item_code,
			"item_name":   item_name_map.get(item_code, ""),
			"qty_stock":   qty_stock,
			"pmp_erpnext": pmp_erpnext,
			"pmp_calcule": pmp_calcule,
			"ecart":       ecart,
		})

	rows.sort(key=lambda r: r["item_code"])
	return rows
