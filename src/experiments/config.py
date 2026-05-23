"""
config.py — Paramètres de simulation (réalistes)

Cohérence énergétique :
  grille       = 3 km × 3 km
  vitesse      = 833 m/slot  (10 km/h en zone urbaine dense)
  conso        = 20 kWh / 100 km
  autonomie    = 300 km (moyenne)
  delta_soc/slot = 833m × (20/100 000) / (20×300/100) = 0.00028 → ~3 600 slots pour vider
  distance max avec soc=0.10 → 0.10×300 km = 30 km >> 3 km de grille ✓
"""
import numpy as np


class SimulationConfig:

    # ------------------------------------------------------------------ GRILLE
    # 3×3 km : taille raisonnable pour une zone urbaine dense.
    # À 10 km/h, une voiture traverse la grille en ~18 slots (90 min).
    C_GRID = 3 * 1e3            # 2000 km^2 (1/5 Paris)

    # ------------------------------------------------------------------ TEMPS
    SLOT_DURATION = 5               # 5 minutes, doit être multiple de 60
    NB_SLOTS_IN_ONE_HOUR = 12       # 60 / SLOT_DURATION
    TOTAL_TIME = 12 #* 24 * 1        # 12 slots de 5min dans une heure, 4 heures

    # ------------------------------------------------------------------ VISUALIZATION
    VISUALIZE = False
    VIS_DELAY = 2 # 100ms entre chaque slot

    # ------------------------------------------------------------------ AGENTS
    NB_CARS       = 50
    NB_SOCIETIES  = 5
    NB_STATIONS   = 40

    # ------------------------------------------------------------------ STATION
    NB_CHARG_SPOT = {'low': 4, 'high': 6}

    w1 = 1.0    # poids profit dans l'objectif station
    w2 = 1.0    # poids pénalité éloignement temporel
    z  = 2.0    # constante de priorité profit (z > 1)

    SOCIETY_UPDATE_INTERVAL = 12 * 12    # mise à jour stratégie toutes <nb_slot>, 2 heures

    # ------------------------------------------------------------------ VOITURE

    # Vitesse réduite : 50 km/h en zone urbaine dense
    # 50 km/h × (5/60) h/slot = 4.167 km/slot = 4.167 m/slot
    CAR_SPEED = 4.167e3             # m / slot

    REDUCE_SPEED_FACTORS = [1.05, 1.25]  # facteurs de réduction si comportement non-présent

    # Probabilités de comportement — somme = 100
    BASE_CANCEL_PROB = {
        'pres':  75,    # présent et honore la réservation
        'abs':   10,    # no-show complet
        'early':  9,    # annulation anticipée (> 2h avant)
        'late':   6,    # annulation tardive (< 2h avant)
        'noise':  0.15  # bruit ±15%
    }
    assert (BASE_CANCEL_PROB['pres'] + BASE_CANCEL_PROB['abs'] +
            BASE_CANCEL_PROB['early'] + BASE_CANCEL_PROB['late']) == 100

    # SOC initial : entre 0.3 et 1.0 (pas de voiture quasi-vide au départ)
    CAR_INIT_SOC = {'low': 0.30, 'high': 0.80}

    # Seuil de déclenchement de la recharge : moyenne 20%, max 35%
    # → une voiture ne cherche jamais à se recharger au-dessus de 35% de batterie
    CAR_SOC_THRESHOLD_PARAMS = {
        'mean': 0.35,
        'sd':   0.06,
        'low':  0.25,
        'high': 0.70
    }

    # Autonomie réaliste : 300-700 km (citadines électriques)
    CAR_AUTONOMY_PARAMS_KM = {
        'mean': 400,
        'sd':    60,
        'low':  300,
        'high': 500
    }

    # Durée de recharge demandée : majoritairement "recharge complète"
    CHARGING_DURATION_PARAMS = [
        (0.9, (0.8, 1.0)),   # recharge quasi-complète
        (0.1, (0.6, 0.8)),   # recharge partielle
    ]

    # Consommation énergétique : 10 kWh / 100 km
    ENERGY_CONSUMPTION = {
        'quantity_kW':     10,          # kWh (5)
        'distance_unit_m': 100 * 1e3    # 100 km en mètres (1000e3)
    }

    # ------------------------------------------------------------------ SOCIÉTÉ
    BASE_POINTS_STRATEGY = {
        'pres':  4.0,
        'abs':   3.0,
        'late':  1.0,
        'early': 0.5
    }

    LATE_CANCEL_REF = 24    # annulation tardive si < 2h = 24 slots

    # ------------------------------------------------------------------ PANNE
    # Seuil en dessous duquel la voiture est considérée en panne (soc ≈ 0)
    SOC_BREAKDOWN_THRESHOLD = 3 * 1e3   # 1% → ~3 km restants

    MIN_RAY_SEARCH = 0        # rayon minimal de recherche d'une station (5km)
    MAX_RAY_SEARCH = 1 * 1e3
    COEFF_MAX_DIST = 0.5            # coeff de max distance définie comme max_ray_search


if __name__ == "__main__":
    
    c = SimulationConfig()
    slot_h = c.SLOT_DURATION / 60
    dist_slot = c.CAR_SPEED          # m/slot
    autonomy_mean = c.CAR_AUTONOMY_PARAMS['mean']
    conso = c.ENERGY_CONSUMPTION['quantity_kW'] / c.ENERGY_CONSUMPTION['distance_unit_m']
    delta_soc = dist_slot * conso / (c.ENERGY_CONSUMPTION['quantity_kW'] * autonomy_mean / 100)

    print(f"Grille            : {c.C_GRID/1e3:.1f} km × {c.C_GRID/1e3:.1f} km")
    print(f"Vitesse           : {c.CAR_SPEED} m/slot  ({c.CAR_SPEED/1000/slot_h:.0f} km/h)")
    print(f"ΔSoC / slot       : {delta_soc:.5f}  ({1/delta_soc:.0f} slots pour vider)")
    print(f"Autonomie moy.    : {autonomy_mean} km")
    print(f"Distance max grille traversée avec soc=0.10 : {0.10*autonomy_mean:.0f} km >> {c.C_GRID/1e3:.1f} km ✓")
