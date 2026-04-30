# Changelog

Tous les changements notables de ce projet sont documentés dans ce fichier.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

---

## [0.2.0] - 2026-04-30

### Modifié
- **Rapport Analyse PMP** : refonte complète de la méthode de calcul du PMP.
  - Passage de Moving Average (PMP glissant) à **FIFO**, identique à la méthode ERPNext.
  - Stock initial basé sur le champ `stock_queue` du dernier SLE avant la date de début (file FIFO réelle).
  - Entrées achat : ajout d'une couche `[qty, prix_HT]` en fin de file.
  - Retours clients : ajout d'une couche au PMP courant de la file.
  - Sorties : consommation des couches les plus anciennes en premier (FIFO).
  - PMP calculé = moyenne pondérée des couches restantes.
  - Seuil d'affichage de l'écart relevé de 0.001 à **0.01** pour filtrer le bruit d'arrondi monétaire ERPNext.

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

## [0.0.1] - 2026-03-26

### Ajouté
- **Rapport État de Stock** : rapport listant tous les articles avec Stock Initial, Entrée, Sortie, Restant, Stock ERPNext et Écart.
  - Stock Initial = stock accumulé avant la date de début choisie.
  - Entrée/Sortie = mouvements dans la période sélectionnée (hors documents annulés).
  - Stock ERPNext = stock actuel depuis tabBin.
  - Écart = Restant − Stock ERPNext (détection des anomalies).
  - Filtre optionnel par Dépôt.

- **Rapport Historique de Mouvement** : rapport détaillé par article sur une période.
  - Stock de départ affiché en première ligne.
  - Mouvements chronologiques avec type, N° document cliquable, Dépôt.
  - Prix Unitaire HT récupéré depuis le document source (net_rate).
  - Stock après chaque mouvement.
  - Entrées en vert, Sorties en rouge.
  - Filtre optionnel par Dépôt.
