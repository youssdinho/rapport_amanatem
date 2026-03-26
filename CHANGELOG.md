## [1.0.0] - 2026-03-26

### Ajouté
- **Etat de Stock** : rapport listant tous les articles avec Stock Initial, Entrée, Sortie, Restant, Stock ERPNext et Ecart
  - Stock Initial = stock accumulé avant la date de début choisie
  - Entrée/Sortie = mouvements dans la période sélectionnée (hors documents annulés)
  - Stock ERPNext = stock actuel depuis tabBin
  - Ecart = Restant − Stock ERPNext (détection des anomalies)
  - Filtre optionnel par Dépôt

- **Historique de Mouvement** : rapport détaillé par article sur une période
  - Stock de départ affiché en première ligne
  - Mouvements chronologiques avec type, N° document cliquable, Dépôt
  - Prix Unitaire HT récupéré depuis le document source (net_rate)
  - Stock après chaque mouvement
  - Entrées en vert, Sorties en rouge
  - Filtre optionnel par Dépôt
