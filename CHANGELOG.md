# Changelog

Tous les changements notables de ce projet sont documentés dans ce fichier.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

---

## [0.1.0] - 2026-03-27

### Ajouté
- **Rapport Analyse PMP** : nouveau rapport de contrôle du Prix Moyen Pondéré (PMP HT).
  - Compare le PMP calculé par ERPNext avec notre propre calcul indépendant.
  - Stock initial basé sur l'état du 31/12/2025 (import stock d'ouverture).
  - Prix des entrées achats récupérés depuis les documents sources (net_rate HT).
  - Retours clients valorisés au PMP courant à la date du retour.
  - Colonne Écart HT mise en évidence (vert = 0, rouge = écart détecté).
  - Filtres : Date Début (défaut 01/01/2026) et Date Fin (défaut aujourd'hui).

---

## [0.0.1] - 2026-03-13

### Ajouté
- **Rapport État de Stock** : stock initial, entrées, sorties, restant vs stock ERPNext avec écart.
- **Rapport Historique de Mouvement** : détail chronologique des mouvements d'un article avec prix HT et stock après mouvement.
