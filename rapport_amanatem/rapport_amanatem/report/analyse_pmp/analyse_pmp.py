"""
Rapport Analyse PMP - Amanatem
==============================
Compare le PMP calculé par ERPNext avec notre propre calcul du PMP.

Méthode de calcul du PMP :
- Stock initial  : dernier état connu AVANT la date de début (qty_after_transaction + valuation_rate ERPNext)
- Entrée achat   : nouveau PMP = (valeur_courante + qté * prix_HT_document) / (qté_courante + qté)
- Retour client  : le prix utilisé = PMP courant à cette date (stock revient au même coût)
- Sortie (vente) : valeur réduite au PMP courant, PMP inchangé
- Retour fournisseur : sortie de stock, PMP inchangé

Sources de prix HT (depuis les documents) :
  Purchase Receipt  → tabPurchase Receipt Item.net_rate
  Purchase Invoice  → tabPurchase Invoice Item.net_rate
  Stock Entry       → tabStock Entry Detail.basic_rate

Tous les prix affichés sont HT.
"""
import frappe
from frappe import _
from frappe.utils import getdate


# Doctypes pouvant avoir le flag is_return
IS_RETURN_DOCTYPES = {"Sales Invoice", "Delivery Note", "Purchase Receipt", "Purchase Invoice"}

# Mapping voucher_type → (table_enfant, champ_prix_ht)
# utilisé pour récupérer le prix HT depuis le document source via voucher_detail_no
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
# Données de base
# ---------------------------------------------------------------------------

def get_opening_state(date_debut):
	"""
	Retourne pour chaque article le dernier état connu AVANT date_debut :
	  - qty  : qty_after_transaction du dernier SLE
	  - pmp  : valuation_rate du dernier SLE
	  - value: qty * pmp
	Cela constitue le point de départ de notre calcul de PMP.
	"""
	rows = frappe.db.sql(
		"""
		SELECT
			sle.item_code,
			sle.qty_after_transaction AS qty,
			sle.valuation_rate        AS pmp
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
		opening[r.item_code] = {
			"qty":   qty,
			"pmp":   pmp,
			"value": qty * pmp,
		}
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
	"""
	Pour les entrées en stock (actual_qty > 0) dont le doctype peut avoir is_return,
	vérifie si le document source est un retour.
	Retourne : dict { (voucher_type, voucher_no) -> bool }
	"""
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
	"""
	Pour les entrées achats (non-retour), récupère le prix HT depuis
	la ligne du document source identifiée par voucher_detail_no.
	Retourne : dict { voucher_detail_no -> prix_ht }
	"""
	by_type = {}
	for m in mouvements:
		if m.actual_qty <= 0:
			continue
		if is_return_map.get((m.voucher_type, m.voucher_no), False):
			continue  # retour → prix = PMP courant, pas besoin du document
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
	"""Quantité et PMP actuels par article depuis tabBin (source ERPNext)."""
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
# Calcul du PMP
# ---------------------------------------------------------------------------

def calculate_pmp(opening, mouvements, is_return_map, prix_map):
	"""
	Calcule notre PMP pour chaque article en traitant les mouvements
	chronologiquement.

	Règles :
	  - Entrée achat    : PMP = (valeur + qté * prix_HT) / (stock + qté)
	  - Retour client   : entrée valorisée au PMP courant → PMP inchangé
	  - Sortie vente    : valeur -= qté_sortie * PMP courant → PMP inchangé
	  - Retour fournisseur : sortie → PMP inchangé
	"""
	state = {
		code: {"qty": o["qty"], "value": o["value"], "pmp": o["pmp"]}
		for code, o in opening.items()
	}

	for m in mouvements:
		code = m.item_code
		if code not in state:
			state[code] = {"qty": 0.0, "value": 0.0, "pmp": 0.0}

		s = state[code]
		qty = m.actual_qty  # positif = entrée, négatif = sortie

		if qty > 0:
			# --- Entrée en stock ---
			key = (m.voucher_type, m.voucher_no)
			if is_return_map.get(key, False):
				# Retour client : valorisé au PMP courant (pas de changement de PMP)
				rate = s["pmp"]
			else:
				# Achat : prix HT depuis le document
				rate = prix_map.get(m.voucher_detail_no or "", 0.0)
				if not rate:
					# Fallback sur incoming_rate ERPNext si prix document absent
					rate = m.incoming_rate or 0.0

			new_qty   = s["qty"] + qty
			new_value = s["value"] + qty * rate
			s["qty"]   = new_qty
			s["value"] = new_value
			s["pmp"]   = new_value / new_qty if new_qty > 0 else s["pmp"]

		elif qty < 0:
			# --- Sortie de stock ---
			# Réduire la valeur au PMP courant ; le PMP ne change pas
			s["value"] = s["value"] + qty * s["pmp"]  # qty est négatif
			s["qty"]   = s["qty"]   + qty
			if s["qty"] <= 0:
				s["qty"]   = 0.0
				s["value"] = 0.0
				# On conserve le pmp en mémoire même à stock zéro

	return state


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def get_data(filters):
	date_debut = filters["date_debut"]
	date_fin   = filters["date_fin"]

	# 1. État initial (dernier SLE avant date_debut)
	opening = get_opening_state(date_debut)

	# 2. Mouvements dans la période
	mouvements = get_mouvements(date_debut, date_fin)

	# 3. Identifier les retours parmi les entrées
	is_return_map = get_is_return_map(mouvements)

	# 4. Prix HT depuis les documents sources (achats uniquement)
	prix_map = get_prix_achat_map(mouvements, is_return_map)

	# 5. Calcul de notre PMP
	pmp_state = calculate_pmp(opening, mouvements, is_return_map, prix_map)

	# 6. Stock et PMP ERPNext depuis tabBin (articles avec stock > 0)
	bin_data = get_bin_data()

	# 7. Noms des articles
	item_name_map = {
		r.name: r.item_name
		for r in frappe.db.sql(
			"SELECT name, item_name FROM `tabItem` WHERE disabled = 0",
			as_dict=True,
		)
	}

	# 8. Construction des lignes (uniquement articles avec stock ERPNext > 0)
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
