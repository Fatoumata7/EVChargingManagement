# Pilote bimodal — analyse des résultats

Ce pilote pose deux questions dans une population fortement hétérogène :

1. Quel est l'apport marginal de la réputation, puis de l'adaptation ?
2. Les scores de réputation distinguent-ils effectivement les deux profils de
   conducteurs ?

Il est **exploratoire** : 5 graines, un seul régime, une seule capacité.

## 1. Configuration

| Paramètre | Valeur |
|---|---|
| Régime | `balance_bimodal` |
| Profil H (125 véhicules) | présence 0,90 ; absence 0,05 ; annulation précoce 0,03 ; annulation tardive 0,02 |
| Profil L (125 véhicules) | présence 0,30 ; absence 0,35 ; annulation précoce 0,21 ; annulation tardive 0,14 |
| Moyenne de la population | 0,60 / 0,20 / 0,12 / 0,08 (régime équilibré) |
| Graines | 1, 2, 3, 4, 5 |
| Flotte | 250 véhicules |
| Infrastructure | 40 stations à 2 chargeurs, 4 opérateurs |
| Horizon | 1 440 créneaux de 5 minutes (5 jours) |
| Méthodes | `multistation`, `multistation_rep`, `bramev`, `load_aware` |
| Simulations | 20 |

- **Probabilités :** fixes, sans le bruit comportemental de ±15 %.
- **Attribution des profils :** par une permutation aléatoire des identifiants,
  tirée dans un flux dédié (`car_profile`). Les véhicules H ne sont pas les
  premiers traités.
- **Information des stations :** elles ne voient que les scores de
  réputation, qui partent tous de zéro.
- **Autres paramètres :** ceux du pilote congestion. Mémoire de 5 événements,
  poids initiaux, barèmes opérateurs, règles de sélection, adaptation,
  mobilité, retraits, limite de 300 s du solveur.
- **Monde initial :** pour chaque graine, il est sauvegardé une fois dans
  `worlds/` et repris par les quatre méthodes.

**Provenance**

| | |
|---|---|
| Commit | `c8a95ba` |
| Dépôt modifié au lancement (`git_dirty`) | `false` |
| Environnement | Python 3.12.0, 8 processus |
| Durée | 8 min 30 s (20:37 → 20:45 UTC) |
| Configuration | `experiments/bimodal_pilot.yaml` |

**Reproduction**

```bash
uv run main.py run --config experiments/bimodal_pilot.yaml --workers 8
uv run python -m src.pipeline.bimodal results_grid/<run>
```

## 2. Contrôles effectués

- **Mondes :** probabilités exactes à 10⁻¹² près, et exactement 125 véhicules
  H et 125 L pour chaque graine.
- **Monde partagé :** les quatre méthodes d'une même graine lisent le même
  fichier `worlds/seed<s>_balance_bimodal_250cars.json`.
- **Contrôles d'implémentation :** les 20 runs les passent, sans diagnostic
  de comportement.
- **Solveur :** toutes les résolutions sont certifiées optimales. Aucune n'est
  arrêtée par la limite de temps, aucune n'échoue.
- **Jointures entre exports, vérifiées sur les 20 cas :**
  - une décision par couple (station, requête) reçu ;
  - offres et décisions en correspondance un pour un ;
  - offres confirmées = réservations ;
  - non-offres = refus des stations ;
  - chaque offre et chaque décision se rattache à une requête unique ;
  - borne du solveur ≥ objectif.
- **Scores :** nuls à l'initialisation, nuls tout au long du run sans
  réputation, et non nuls avec. Les véhicules retirés sont conservés dans
  les exports.
- **Reproductibilité :** les résultats sont identiques à ceux d'un premier
  lancement du même code, à l'exception des temps mesurés à l'horloge.
  L'enregistrement des diagnostics ne modifie pas la simulation : un cas du
  pilote congestion rejoué avec les diagnostics reproduit son résultat
  enregistré.

## 3. Définitions

Les définitions sont celles du papier, calculées à partir des
enregistrements par requête :

| Notation | Définition |
|---|---|
| S_del | moyenne sur toutes les requêtes de min(1, E_del/E_req) ; une requête non servie compte 0 |
| S_full | part des requêtes avec E_del ≥ E_req − 10⁻³ kWh |
| E_tot | énergie totale délivrée |
| I_held | part de la capacité réservée restée inutilisée |
| U | utilisation effective, moyenne par station |
| O_m | occupation réservée de la station m |
| Délai programmé | délai moyen des réservations confirmées |
| Retraits | véhicules retirés définitivement après épuisement de leurs tentatives |

Statistiques :
- **Unité de réplication :** la graine.
- **Différences :** calculées à l'intérieur de chaque graine, avec un
  intervalle de Student à 95 % sur 4 degrés de liberté (t = 2,776).
- **Correction de Holm :** à 5 %, sur S_del, S_full et E_tot, en deux
  familles distinctes de 3 tests (réputation, adaptation).
- **Comparaison avec Load-aware et résultats par profil :** descriptifs.

## 4. Résultats par méthode

Moyenne ± demi-largeur de l'intervalle à 95 % sur les 5 graines :

| Indicateur | Multi-station | MS + Rep. | BRAM-EV | Load-aware |
|---|---:|---:|---:|---:|
| S_del (%) | 45,17 ± 1,48 | 45,61 ± 1,42 | 45,58 ± 1,54 | **46,83 ± 1,09** |
| S_full (%) | 29,79 ± 2,40 | 31,14 ± 3,06 | 30,87 ± 2,75 | **34,19 ± 1,50** |
| E_tot (MWh) | 23,92 ± 0,48 | 23,97 ± 0,55 | 23,87 ± 0,60 | **24,29 ± 0,91** |
| I_held (%) | 29,12 ± 1,51 | 28,75 ± 1,43 | 28,80 ± 1,44 | 29,15 ± 1,13 |
| U (%) | 36,06 ± 1,08 | 36,14 ± 1,00 | 36,03 ± 1,12 | 36,65 ± 1,18 |
| O_m moyen (%) | 50,88 ± 1,16 | 50,73 ± 1,44 | 50,61 ± 1,28 | 51,73 ± 1,45 |
| O_m maximum (%) | 96,55 ± 0,94 | 94,92 ± 1,93 | 95,77 ± 1,56 | 91,38 ± 2,95 |
| Délai programmé (min) | 25,37 ± 4,86 | 25,76 ± 5,64 | 25,96 ± 4,92 | 20,07 ± 3,64 |
| Requêtes | 2 427 ± 69 | 2 412 ± 75 | 2 406 ± 86 | 2 375 ± 60 |
| Retraits | 7,6 ± 6,2 | 7,2 ± 1,8 | 6,2 ± 1,4 | 8,0 ± 0,9 |

La capacité est sous tension. La station la plus chargée a 91 à 97 % de ses
créneaux réservés, et près de 29 % de la capacité réservée reste
inutilisée, à cause des absences et des annulations.

## 5. Effet des composants

Différence par graine (méthode d'arrivée − méthode de départ), moyenne,
intervalle à 95 % et p ajustée par Holm :

| Contraste | Critère | g1 | g2 | g3 | g4 | g5 | Moyenne [IC 95 %] | p | p Holm |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|
| **Réputation** (MS + Rep. − MS) | S_del (pts) | +0,91 | −0,07 | +0,77 | +0,28 | +0,34 | +0,45 [−0,04 ; +0,94] | 0,065 | 0,13 |
| | S_full (pts) | +1,74 | +1,58 | −0,07 | +1,54 | +1,95 | +1,35 [+0,34 ; +2,35] | 0,020 | 0,061 |
| | E_tot (MWh) | +0,11 | +0,02 | +0,32 | −0,03 | −0,20 | +0,05 [−0,19 ; +0,28] | 0,62 | 0,62 |
| **Adaptation** (BRAM-EV − MS + Rep.) | S_del (pts) | −0,11 | +0,03 | −0,11 | +0,72 | −0,71 | −0,04 [−0,67 ; +0,60] | 0,88 | 1 |
| | S_full (pts) | −0,29 | −0,34 | +0,66 | +0,23 | −1,63 | −0,28 [−1,35 ; +0,79] | 0,51 | 1 |
| | E_tot (MWh) | −0,26 | +0,12 | −0,39 | +0,00 | +0,02 | −0,10 [−0,37 ; +0,16] | 0,34 | 1 |
| **BRAM-EV − Load-aware** (descriptif) | S_del (pts) | −0,79 | −1,31 | −2,26 | −0,55 | −1,32 | −1,25 [−2,07 ; −0,43] | — | — |
| | S_full (pts) | −1,45 | −3,37 | −4,04 | −3,49 | −4,26 | −3,32 [−4,70 ; −1,94] | — | — |
| | E_tot (MWh) | −0,50 | −0,76 | −0,61 | −0,31 | +0,07 | −0,42 [−0,82 ; −0,03] | — | — |

![Effets de la réputation sur S_del](bimodal/figures/reputation_effects_S_del.png)

**Réputation**
- L'effet est positif pour 4 graines sur 5, sur S_del comme sur S_full.
- Sur S_full, l'intervalle exclut zéro point par point (+1,35 point).
- Aucun critère n'est significatif après correction de Holm : la plus petite
  p ajustée vaut 0,061.
- L'énergie totale délivrée ne change pas.
- Les effets sont plus grands que dans la campagne principale, où tous les
  intervalles de l'effet de réputation sur S_del restaient dans ±0,41
  point. Ils restent petits devant l'effet de la règle de sélection des
  offres.
- Les effets sur les ressources sont négligeables : I_held −0,37 point
  [−0,90 ; +0,16], délai programmé +0,38 min [−0,72 ; +1,49], retraits −0,4
  [−5,2 ; +4,4].

**Adaptation**
- Aucun effet mesurable sur les trois critères. Les signes changent d'une
  graine à l'autre, et les p ajustées valent 1.

**Load-aware**
- Load-aware fait mieux que BRAM-EV sur les trois critères, pour les 5
  graines en S_full et pour 4 graines sur 5 en E_tot.
- Il le fait avec un délai programmé plus court (BRAM-EV attend en moyenne
  5,9 min de plus, IC [+4,4 ; +7,4]) et une charge moins concentrée (O_m
  maximum 91 % contre 96 %).
- Comme dans la campagne principale, la règle de sélection des offres pèse
  davantage que la réputation.

## 6. Service par profil

Moyenne ± demi-largeur de l'intervalle à 95 %, sur 5 graines :

| Méthode | Profil | Requêtes | S_del (%) | S_full (%) | E_tot (MWh) | Retraits |
|---|---|---:|---:|---:|---:|---:|
| Multi-station | H | 940 ± 13 | 76,57 ± 1,86 | 50,80 ± 3,61 | 14,92 ± 0,25 | 3,6 ± 3,4 |
| Multi-station | L | 1 487 ± 61 | 25,30 ± 1,38 | 16,50 ± 1,44 | 9,01 ± 0,49 | 4,0 ± 3,6 |
| MS + Rep. | H | 940 ± 12 | 76,91 ± 2,59 | 52,32 ± 5,12 | 14,99 ± 0,28 | 3,0 ± 0,9 |
| MS + Rep. | L | 1 472 ± 70 | 25,60 ± 0,70 | 17,58 ± 1,29 | 8,98 ± 0,55 | 4,2 ± 2,2 |
| BRAM-EV | H | 935 ± 23 | 77,38 ± 2,64 | 52,27 ± 3,80 | 14,99 ± 0,33 | 2,8 ± 1,0 |
| BRAM-EV | L | 1 471 ± 74 | 25,33 ± 0,98 | 17,23 ± 1,48 | 8,88 ± 0,59 | 3,4 ± 0,7 |
| Load-aware | H | 919 ± 12 | 79,39 ± 1,44 | 57,76 ± 1,92 | 15,11 ± 0,27 | 2,8 ± 1,4 |
| Load-aware | L | 1 456 ± 59 | 26,25 ± 1,18 | 19,29 ± 1,18 | 9,18 ± 0,76 | 5,2 ± 1,0 |

- **Écart de service entre profils :** le service est environ trois fois
  plus élevé pour H, quelle que soit la méthode. Les véhicules L émettent
  aussi beaucoup plus de requêtes (environ 1 470 contre 940), probablement
  parce qu'une absence ou une annulation laisse le besoin de recharge
  entier. Ce point n'a pas été vérifié dans les données.
- **Effet de la réputation par profil (descriptif) :**
  - S_full augmente pour les deux profils : H +1,51 point [−1,25 ; +4,28],
    L +1,09 point [+0,88 ; +1,29], ce dernier gain étant positif pour les
    5 graines ;
  - l'énergie délivrée aux H augmente légèrement : +0,07 MWh [+0,01 ; +0,13].
- La réputation ne réduit donc pas le service des véhicules L : leur S_full
  progresse aussi.

## 7. Les scores distinguent-ils H et L ?

Oui, nettement, et de plus en plus au fil des jours.

| Méthode | Jour | Écart H − L (selon l'opérateur) | P(score H > score L) |
|---|---:|---|---|
| MS + Rep. | 1 | +0,19 à +0,21 | 0,79 à 0,83 |
| MS + Rep. | 5 | +0,35 à +0,39 | 0,86 à 0,87 |
| BRAM-EV | 1 | +0,18 à +0,21 | 0,80 à 0,82 |
| BRAM-EV | 5 | +0,36 à +0,38 | 0,86 à 0,88 |

- Les valeurs sont les moyennes sur 5 graines, pour les historiques non vides.
- P(score H > score L) est la probabilité qu'un score H tiré au hasard
  dépasse un score L du même opérateur. 0,5 signifierait aucune séparation.
- Le détail par graine est dans `bimodal/score_separation.csv` : l'écart y
  va de 0,12 à 0,50 et la probabilité de 0,74 à 0,92.

![Évolution des scores H/L](bimodal/figures/scores_by_profile.png)

- **Couverture des historiques :** avec `multistation_rep`, la part des
  couples véhicule–opérateur ayant un historique passe de 34 % le jour 1 à
  84 % le jour 5 pour H, et de 53 % à 87 % pour L.
- **Nature du score :** il traduit un historique d'événements signé, pas une
  probabilité de présence calibrée. Un écart de score entre profils ne
  constitue donc pas une estimation de leur fiabilité.

## 8. Pourquoi une bonne séparation change si peu l'allocation

**Les scores L restent proches de zéro**, entre −0,06 et +0,01 selon
l'opérateur et le jour. Or zéro est aussi le score d'un véhicule sans
historique.

C'est un effet des barèmes. Après normalisation, les valeurs d'événement
sont : présence +1, absence −3/4, annulation tardive −1/4, annulation
précoce −1/8. La valeur attendue d'un événement vaut :

| Profil | Barème de base | 20 barèmes perturbés des opérateurs |
|---|---|---|
| L | −0,02 | de −0,23 à +0,13 |
| H | +0,85 | de +0,59 à +0,88 |

La présence (+1, 30 % des cas) compense presque l'absence (−3/4, 35 % des
cas). **La réputation valorise donc les H, mais ne pénalise pratiquement pas
les L**, qui restent indiscernables d'un véhicule inconnu.

Les décisions des stations le confirment (moyenne sur 5 graines) :

| Méthode | Profil | Taux d'offre | Historique connu | Score lu (historique connu) | Durée offerte / demandée |
|---|---|---:|---:|---:|---:|
| Multi-station | H | 85,0 % | — | — | 66,5 % |
| Multi-station | L | 88,6 % | — | — | 69,8 % |
| MS + Rep. | H | 87,8 % | 53,8 % | +0,268 | 69,5 % |
| MS + Rep. | L | 89,2 % | 68,3 % | +0,001 | 69,8 % |
| BRAM-EV | H | 88,1 % | 54,2 % | +0,262 | 69,8 % |
| BRAM-EV | L | 89,5 % | 68,3 % | +0,001 | 69,7 % |

- Avec la réputation, le taux d'offre aux H progresse (85,0 → 87,8 %), mais
  les L reçoivent toujours autant d'offres, et la même part de la durée
  demandée.
- Le score n'entre dans l'objectif de la station qu'avec le poids (1 − α),
  face à une récompense C = 2 pondérée par α. Avec des scores L proches de
  zéro, il ne peut pas écarter ces véhicules.

## 9. Interprétation

- **Séparation des profils :** dans une population fortement hétérogène, les
  scores séparent clairement les deux profils, au sein de chaque opérateur
  et dès le premier jour. L'information comportementale existe donc dans
  les historiques.
- **Effet de la réputation :** il est positif et un peu plus grand que dans
  la campagne principale (S_full +1,35 point, positif pour 4 graines sur 5).
  Il **n'est pas établi** après correction de Holm sur les trois critères de
  service, et l'énergie totale délivrée ne change pas.
- **Effet de l'adaptation :** aucun.
- **Load-aware :** une règle simple, qui choisit la station la moins chargée,
  fait mieux que BRAM-EV sur tous les critères de service.
- **Mécanisme probable :** la séparation des scores se traduit peu dans
  l'allocation parce que les barèmes laissent les conducteurs peu fiables
  autour de zéro, au niveau d'un véhicule inconnu. L'écart de service entre
  profils vient du comportement des conducteurs, pas de l'allocation.

Formulation proposée pour le papier : la réputation identifie les profils
mais n'apporte pas de gain de service établi dans la population bimodale
évaluée ; l'adaptation n'apporte rien ; la règle de sélection des offres
reste le facteur dominant.

## 10. Limites

- Pilote exploratoire : 5 graines, un régime, une capacité. Une absence de
  significativité n'établit pas une équivalence.
- **Contrôle manquant :** pour attribuer à l'hétérogénéité seule l'écart avec
  les anciens résultats, il faudrait le même plan sous le régime équilibré,
  avec la même capacité et les mêmes 5 graines.
- **Horizon :** cinq jours. Les historiques sont encore incomplets au début
  (34 % des couples H ont un historique le jour 1).
- **Barèmes :** l'effet dépend de leur forme. Des barèmes qui pénalisent
  davantage l'absence rendraient les scores L négatifs. Ce test n'a pas été
  fait ici.

## 11. Fichiers

| Fichier | Contenu |
|---|---|
| `params.json`, `manifest.json` | paramètres résolus ; commit, durée, contrôles par cas |
| `worlds/`, `grids/`, `fleets/` | mondes initiaux (profils et probabilités de chaque véhicule dans `worlds/`) |
| `results/<cas>.json` | résultat complet de chaque cas |
| `tables/<cas>_latency.csv` | une ligne par requête : énergie demandée et délivrée, issue |
| `tables/<cas>_profiles.csv` | profil et probabilités de chaque véhicule |
| `tables/<cas>_decisions.csv` | décisions des stations, non-offres comprises : score lu, longueur d'historique, alpha, durées demandée et offerte |
| `tables/<cas>_ilp_batches.csv` | lots du solveur : taille, capacité libre candidate, statut, objectif, borne, temps |
| `tables/<cas>_offers.csv` | offres, rang, tentative de confirmation et devenir |
| `tables/<cas>_scores.csv` | scores de tous les couples véhicule–opérateur, à l'initialisation puis chaque jour |
| `bimodal/README.md` | tableaux générés automatiquement (pleine précision dans les CSV) |
| `bimodal/methods.csv`, `profiles.csv`, `paired.csv`, `paired_per_seed.csv` | statistiques des sections 4 à 6 |
| `bimodal/score_levels.csv`, `score_separation.csv`, `decisions_by_profile.csv` | statistiques des sections 7 et 8 |
| `bimodal/figures/` | les deux figures |

Les tableaux, statistiques et figures de `summary.csv`, `paired.csv`,
`ablation*.csv` et `figures/` à la racine sont ceux produits automatiquement
par le pipeline à la fin du run. Ils utilisent les anciens noms
d'indicateurs ; l'analyse ci-dessus s'appuie sur `bimodal/`.
