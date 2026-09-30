# Ré-analyse de `20260926T223707Z_seeds1-2-3-4+6_ablation`

Ce dossier **ne contient aucune nouvelle simulation**. Tous les indicateurs sont
recalculés à partir des sorties du run source :

- `results/<tag>.json` : résultat complet de chaque cas ;
- `tables/<tag>_latency.csv` : une ligne par requête, avec l'énergie demandée et
  l'énergie délivrée ;
- `tables/<tag>_acceptances.csv` : distance et attente de chaque réservation.

Pour régénérer le dossier :

```bash
python -m src.pipeline.reanalysis \
    "results_grid/20260926T223707Z_seeds1-2-3-4+6_ablation" \
    "results_grid/20260926T223707Z_seeds1-2-3-4+6_ablation_modified"
```

Le run source couvre 10 graines × 3 scénarios × 3 tailles de flotte
(50 / 150 / 250 véhicules) × 8 méthodes, soit 720 cas. Les grilles, les flottes,
les résultats bruts et les figures restent dans le dossier source.

## 1. Indicateurs de service

| Colonne | Définition | Dénominateur |
|---|---|---|
| `served_rate` *(anciennement `satisfied_rate`)* | Requête **servie, même partiellement** : au moins un créneau de recharge a été délivré. | toutes les requêtes |
| `fully_satisfied_rate` *(nouveau)* | Requête **entièrement satisfaite** : `énergie délivrée ≥ énergie demandée − 0,001 kWh`. | toutes les requêtes |
| `fully_satisfied_share_of_served` *(nouveau)* | Part des requêtes servies qui sont entièrement satisfaites. | requêtes servies |
| `service_ratio_mean` | Moyenne de `min(1, délivrée / demandée)`. Une requête non servie compte 0. | toutes les requêtes |
| `service_ratio_mean_served` *(anciennement `service_ratio_mean_satisfied`)* | Même ratio, restreint aux requêtes servies. | requêtes servies |

Seul le nom de `served_rate` change : la définition reste celle du run source.
L'ancien nom laissait penser que le besoin était entièrement couvert, alors
qu'une session écourtée ou une offre partielle compte aussi comme servie.

Colonnes renommées dans `summary.csv` : `nb_demands_satisfied → nb_demands_served`,
`satisfied_rate → served_rate`,
`service_ratio_mean_satisfied → service_ratio_mean_served`.

### Tolérance numérique de la satisfaction complète

`FULL_SERVICE_TOL_KWH = 1e-3` kWh (1 Wh), défini dans `src/pipeline/reanalysis.py`.

- Le simulateur stocke les énergies par requête arrondies à 1e-4 kWh. Leur
  différence est donc connue à ±1e-4 kWh près, et 1 Wh couvre cet écart avec
  de la marge.
- Un créneau de recharge délivre environ 0,7 kWh, soit environ 700 fois la
  tolérance. La tolérance ne peut donc pas transformer un créneau manquant en
  satisfaction complète.
- `full_service_sensitivity.csv` recalcule l'indicateur pour chaque cas avec
  les tolérances 0 / 1e-4 / 1e-3 / 1e-2 / 1e-1 kWh. Moyenne sur les 720 cas :
  47,18 % / 47,18 % / 47,20 % / 47,29 % / 48,10 %. Passer de 0 à 1e-3 kWh
  change le résultat de 0,02 point.

### Occupation des points de recharge (niveau réseau)

`nb_chargers`, `network_occupancy_rate` (créneaux réservés encore tenus /
capacité) et `network_service_rate` (créneaux effectivement utilisés pour
charger / capacité) sont calculés sur l'ensemble du réseau, pondérés par la
capacité. Les moyennes par station (`mean_occupancy_rate`,
`mean_service_rate`) donnent le même poids à une station de 4 et de 6 points.

## 2. Précision

- Les taux sont recalculés **à partir des comptages** des JSON de résultats,
  sans relire les taux arrondis à 4 décimales de l'ancien `summary.csv`. C'est
  le cas des taux servi / annulé / en cours / abandon, réponse / confirmation,
  absence d'offre, rejet (station et requête), gaspillage de créneaux, taux de
  présence et d'intention, et part de véhicules exclus.
- La distance moyenne et l'attente moyenne sont recalculées réservation par
  réservation à partir de `acceptances.csv`.
- Les moyennes, écarts-types, IC 95 % (Student, n − 1 ddl), écarts appariés,
  t, p et `share_improved` sont écrits **sans arrondi** dans tous les CSV.
  Le pipeline (`ablation.py`, `aggregate.py`) n'arrondit plus non plus les
  tables qu'il écrit.
- L'arrondi n'intervient que dans `tables_display/*.md`, pour l'affichage.
- Certaines valeurs n'existent qu'arrondies dans le run source et sont
  utilisées telles quelles : énergies par requête (1e-4 kWh), énergies par
  station (0,1 kWh, donc `energy_delivery_rate`), taux par station (4
  décimales, donc `mean_occupancy_rate` et apparentés), couverture de
  planification et latences. Il faudrait relancer les simulations pour
  gagner en précision sur ces valeurs.
- Contrôle automatique : pour chaque cas, `service_ratio_mean` recalculé est
  comparé à la valeur stockée dans le JSON (écart < 1e-3). Le nombre de
  requêtes servies est aussi comparé entre le JSON et la table par requête.

## 3. Résolutions du MILP non optimales

`nb_ilp_not_optimal` compte les résolutions dont l'optimalité n'est pas
prouvée. `nb_ilp_failed` compte celles qui n'ont renvoyé aucune solution. La
nouvelle colonne `nb_ilp_feasible_time_limit` est leur différence : ce sont les
résolutions arrêtées par la limite de temps (5 min, `ILP_TIME_LIMIT_MS`) avec
une solution réalisable, qui a bien été utilisée pour produire des offres.

| | Nombre |
|---|---|
| Résolutions non prouvées optimales | 84 |
| dont réalisables à la limite de temps | **84** |
| dont véritables échecs (aucune solution) | **0** |

- Les 84 cas concernent tous la flotte de 250 véhicules, 4 couples
  (graine, station) seulement : station 15 / graine 1, station 28 / graine 9,
  stations 7 et 14 / graine 10. Chacun apparaît une fois dans chacune des
  7 méthodes à recherche multi-stations et dans chacun des 3 scénarios
  (4 × 7 × 3 = 84).
- Le Nearest (`greedy`) n'est jamais concerné, puisqu'il n'envoie qu'une
  requête à la fois à la station la plus proche.
- Aucune requête n'a donc été rejetée à cause d'un échec du solveur.
  L'incumbent obtenu à la limite de temps peut cependant dépendre de la charge
  de la machine : les cas concernés sont listés station par station dans
  `solver_status.csv` et résumés dans `tables_display/solver_status.md`.

## 4. Correction de Holm

Une famille par contraste de l'échelle d'ablation (recherche multi-stations,
réputation, adaptation) : 9 configurations (3 scénarios × 3 flottes) × 3
indicateurs (`served_rate`, `fully_satisfied_rate`, `service_ratio_mean`) =
27 tests t appariés (10 graines), α = 0,05. Après correction : 15/27 tests
significatifs pour la recherche multi-stations, 0/27 pour la réputation et
0/27 pour l'adaptation (plus petite p ajustée : 0,51).

## 5. Contenu

| Fichier | Contenu |
|---|---|
| `summary.csv` | une ligne par cas (720), colonnes renommées et complétées, pleine précision ; mêmes colonnes que le pilote congestion |
| `summary_mean.csv` | moyenne, écart-type, IC 95 % par (scénario, flotte, méthode, métrique) |
| `paired.csv` | écarts appariés par graine : échelle d'ablation, baselines, variantes |
| `ablation.csv` / `ablation_mean.csv` | écarts monde par monde / moyennés sur tous les mondes |
| `holm_ladder.csv` | tests t appariés de l'échelle d'ablation, correction de Holm par contraste (27 tests : 9 configurations × 3 indicateurs de service) |
| `solver_status.csv` | stations ayant au moins une résolution non optimale |
| `full_service_sensitivity.csv` | `fully_satisfied_rate` selon la tolérance |
| `tables_display/service_means.md` | les 4 indicateurs de service, moyenne ± demi-largeur IC, en % |
| `tables_display/paired_{ladder,baseline,variant}.md` | écarts appariés en points de %, IC, p, verdict |
| `tables_display/solver_status.md` | résolutions non optimales par cas |
| `tables_display/holm_ladder.md` | tests corrigés par Holm, arrondis pour l'affichage |
| `params.json` | copie des paramètres du run source |
| `manifest.json` | provenance, tolérance, renommages, bilan du solveur |
| `figures/*.png` | figures régénérées depuis le nouveau `summary.csv` (35 figures) |

Les figures qui changent par rapport au run source :

- `satisfaction_<scénario>.png` : 3 panneaux (requêtes servies, requêtes
  entièrement satisfaites, part du besoin énergétique satisfaite) ;
- `overview_satisfaction.png` : 2 lignes (servies / entièrement satisfaites) ;
- `ablation_ladder_<scénario>.png` : servies, entièrement satisfaites, no-show ;
- `ablation_components.png` : panneau « Demands fully satisfied » ajouté.

Les figures de grille et de flotte sont tracées à partir des tables
d'environnement du run source. Pour régénérer uniquement les figures :

```bash
python -m src.pipeline.reanalysis --figures-only \
    "results_grid/20260926T223707Z_seeds1-2-3-4+6_ablation" \
    "results_grid/20260926T223707Z_seeds1-2-3-4+6_ablation_modified"
```
