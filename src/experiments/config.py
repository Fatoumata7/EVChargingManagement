"""
config.py — Paramètres de simulation (réalistes)
"""
import numpy as np


class SimulationConfig:

    # ------------------------------------------------------------------ GRILLE
    # 3×3 km : taille raisonnable pour une zone urbaine dense.
    C_GRID = 3 * 1e3            # 2000 km^2 (1/5 Paris)

    # ------------------------------------------------------------------ TEMPS
    SLOT_DURATION = 5               # 5 minutes, doit être multiple de 60
    NB_SLOTS_IN_ONE_HOUR = 12       # 60 / SLOT_DURATION

    # ------------------------------------------------------------------ VISUALIZATION
    VIS_DELAY = 0.4

    # ------------------------------------------------------------------ APPRENTISSAGE
    GAMMA = 0.1

    # ------------------------------------------------------------------ VOITURE
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

    # Autonomie réaliste : 300-500 km (citadines électriques)
    CAR_AUTONOMY_PARAMS_KM = {
        'mean': 400,
        'sd':    60,
        'low':  300,
        'high': 500
    }

    LATE_CANCEL_REF = 24    # annulation tardive si < 2h = 24 slots

    # Consommation énergétique : 10 kWh / 100 km
    ENERGY_CONSUMPTION = {
        'quantity_kW':     10,          # kWh (5)
        'distance_unit_m': 100 * 1e3    # 100 km en mètres (1000e3)
    }

    # ------------------------------------------------------------------ PANNE
    # Seuil en dessous duquel la voiture est considérée en panne (soc ≈ 0)
    SOC_BREAKDOWN_THRESHOLD = 3 * 1e3   # 1% → ~3 km restants


    def __init__(self):

        self.TOTAL_TIME = 12 * 4 # 12 * 24 * 5        # 12 slots de 5min dans une heure, 4 heures

        self.VISUALIZE = True

        self.NB_CARS       = 50
        self.NB_SOCIETIES  = 5
        self.NB_STATIONS   = 40

        self.w1 = 1.0    # poids profit dans l'objectif station
        self.w2 = 1.0    # poids pénalité éloignement temporel
        self.z  = 2.0    # constante de priorité profit (z > 1)

        self.NB_CHARG_SPOT = {'low': 4, 'high': 6}      # nombre de bornes par station
        self.SOCIETY_UPDATE_INTERVAL = 12 * 12          # mise à jour stratégie toutes <nb_slot>, 2 heures

        # Vitesse réduite : 50 km/h en zone urbaine dense
        # 50 km/h × (5/60) h/slot = 4.167 km/slot = 4.167 m/slot
        self.CAR_SPEED = 4.167e3             # m / slot

        # Rayon de recherche pour l'émission d'une demande
        self.MIN_RAY_SEARCH = 0        # rayon minimal de recherche d'une station (5km)
        self.MAX_RAY_SEARCH = 1 * 1e3
        self.COEFF_MAX_DIST = 0.5            # coeff de max distance définie comme max_ray_search

        self.REDUCE_SPEED_FACTORS = [1.05, 1.25]  # facteurs de réduction si comportement non-présent

        # Probabilités de comportement
        self.BASE_CANCEL_PROB = {
            'pres':  75,    # présent et honore la réservation
            'abs':   10,    # no-show complet
            'early':  9,    # annulation anticipée (> 2h avant)
            'late':   6,    # annulation tardive (< 2h avant)
            'noise':  0.15  # bruit ±15%
        }
        assert (self.BASE_CANCEL_PROB['pres'] + self.BASE_CANCEL_PROB['abs'] +
                self.BASE_CANCEL_PROB['early'] + self.BASE_CANCEL_PROB['late']) == 100

        # Durée de recharge demandée : majoritairement "recharge complète"
        self.CHARGING_DURATION_PARAMS = [
            (0.9, (0.8, 1.0)),   # recharge quasi-complète -> 90% des véhicules demande entre 80-100% de batterie
            (0.1, (0.6, 0.8)),   # recharge partielle      -> 10% des véhicules demande entre 60-80% de batterie
        ]

        # ------------------------------------------------------------------ SOCIÉTÉ
        self.BASE_POINTS_STRATEGY = {
            'pres':  4.0,
            'abs':   3.0,
            'late':  1.0,
            'early': 0.5,
        }
        self.STRATEGY_NOISE = 0.5

        self.log_iter = 10

    def set_TOTAL_TIME(self, value: int) -> None:
        """
        Définit le temps total de simulation.

        Parameters
        ----------
        value : int
            Nombre total de slots (> 0)
        """
        if not isinstance(value, int):
            raise TypeError(
                f"TOTAL_TIME doit être un entier, reçu : {type(value).__name__}"
            )
        if value <= 0:
            raise ValueError(
                f"TOTAL_TIME doit être strictement positif, reçu : {value}"
            )
        self.TOTAL_TIME = value
        

    def set_VISUALIZE(self, value: bool) -> None:
        """
        Active ou désactive la visualisation.
        """
        if type(value) is not bool:
            raise TypeError(
                f"VISUALIZE doit être un bool, reçu : {type(value).__name__}"
            )
        self.VISUALIZE = value


    def set_NB_CARS(self, value: int) -> None:

        if type(value) is not int:
            raise TypeError(
                f"NB_CARS doit être un int, reçu : {type(value).__name__}"
            )

        if value <= 0:
            raise ValueError(
                f"NB_CARS doit être > 0, reçu : {value}"
            )

        self.NB_CARS = value


    def set_NB_SOCIETIES(self, value: int) -> None:

        if type(value) is not int:
            raise TypeError(
                f"NB_SOCIETIES doit être un int, reçu : {type(value).__name__}"
            )

        if value <= 0:
            raise ValueError(
                f"NB_SOCIETIES doit être > 0, reçu : {value}"
            )

        self.NB_SOCIETIES = value


    def set_NB_STATIONS(self, value: int) -> None:

        if type(value) is not int:
            raise TypeError(
                f"NB_STATIONS doit être un int, reçu : {type(value).__name__}"
            )

        if value <= 0:
            raise ValueError(
                f"NB_STATIONS doit être > 0, reçu : {value}"
            )

        self.NB_STATIONS = value


    def set_CAR_SPEED(self, value: float) -> None:

        if not isinstance(value, (int, float)):
            raise TypeError(
                f"CAR_SPEED doit être numérique, reçu : {type(value).__name__}"
            )

        if value <= 0:
            raise ValueError(
                f"CAR_SPEED doit être > 0, reçu : {value}"
            )

        self.CAR_SPEED = float(value)


    def set_BASE_CANCEL_PROB(self, value: dict) -> None:

        required_keys = {
            'pres',
            'abs',
            'early',
            'late',
            'noise'
        }

        if not isinstance(value, dict):
            raise TypeError(
                f"BASE_CANCEL_PROB doit être un dict, reçu : {type(value).__name__}"
            )

        missing = required_keys - set(value.keys())

        if missing:
            raise ValueError(
                f"Clés manquantes : {missing}"
            )

        total = (
            value['pres']
            + value['abs']
            + value['early']
            + value['late']
        )

        if total != 100:
            raise ValueError(
                f"La somme des probabilités doit valoir 100, reçu : {total}"
            )

        if value['noise'] < 0:
            raise ValueError(
                "noise doit être >= 0"
            )

        self.BASE_CANCEL_PROB = value.copy()


    def set_BASE_POINTS_STRATEGY(self, value: dict) -> None:

        required_keys = {
            'pres',
            'abs',
            'late',
            'early'
        }

        if not isinstance(value, dict):
            raise TypeError(
                f"BASE_POINTS_STRATEGY doit être un dict, reçu : {type(value).__name__}"
            )

        missing = required_keys - set(value.keys())

        if missing:
            raise ValueError(
                f"Clés manquantes : {missing}"
            )

        for k, v in value.items():

            if not isinstance(v, (int, float)):
                raise TypeError(
                    f"La valeur associée à '{k}' doit être numérique"
                )

            if v <= 0:
                raise ValueError(
                    f"La valeur associée à '{k}' doit être > 0"
                )

        self.BASE_POINTS_STRATEGY = value.copy()


    def set_STRATEGY_NOISE(self, value: float) -> None:

        if not isinstance(value, (int, float)):
            raise TypeError(
                f"STRATEGY_NOISE doit être numérique, reçu : {type(value).__name__}"
            )

        if value < 0:
            raise ValueError(
                "STRATEGY_NOISE doit être >= 0"
            )

        self.STRATEGY_NOISE = float(value)


    def set_NB_CHARG_SPOT(self, value: dict) -> None:

        required_keys = {'low', 'high'}

        if not isinstance(value, dict):
            raise TypeError(
                f"NB_CHARG_SPOT doit être un dict, reçu : {type(value).__name__}"
            )

        missing = required_keys - set(value.keys())

        if missing:
            raise ValueError(
                f"Clés manquantes : {missing}"
            )

        low = value['low']
        high = value['high']

        if type(low) is not int or type(high) is not int:
            raise TypeError(
                "low et high doivent être des int"
            )

        if low <= 0 or high <= 0:
            raise ValueError(
                "low et high doivent être > 0"
            )

        if low > high:
            raise ValueError(
                "low doit être <= high"
            )

        self.NB_CHARG_SPOT = value.copy()


    def set_SEARCH_RADIUS(
        self,
        min_ray: float,
        max_ray: float
    ) -> None:

        if not isinstance(min_ray, (int, float)):
            raise TypeError("min_ray doit être numérique")

        if not isinstance(max_ray, (int, float)):
            raise TypeError("max_ray doit être numérique")

        if min_ray < 0:
            raise ValueError("min_ray doit être >= 0")

        if max_ray <= 0:
            raise ValueError("max_ray doit être > 0")

        if min_ray > max_ray:
            raise ValueError(
                "min_ray doit être <= max_ray"
            )

        self.MIN_RAY_SEARCH = float(min_ray)
        self.MAX_RAY_SEARCH = float(max_ray)

    def set_log_iter(self, value):

        self.log_iter = value

    

if __name__ == "__main__":
    
    c = SimulationConfig()
    slot_h = c.SLOT_DURATION / 60
    dist_slot = c.CAR_SPEED          # m/slot
    autonomy_mean = c.CAR_AUTONOMY_PARAMS_KM['mean']
    conso = c.ENERGY_CONSUMPTION['quantity_kW'] / c.ENERGY_CONSUMPTION['distance_unit_m']
    delta_soc = dist_slot * conso / (c.ENERGY_CONSUMPTION['quantity_kW'] * autonomy_mean / 100)

    print(f"Grille            : {c.C_GRID/1e3:.1f} km × {c.C_GRID/1e3:.1f} km")
    print(f"Vitesse           : {c.CAR_SPEED} m/slot  ({c.CAR_SPEED/1000/slot_h:.0f} km/h)")
    print(f"ΔSoC / slot       : {delta_soc:.5f}  ({1/delta_soc:.0f} slots pour vider)")
    print(f"Autonomie moy.    : {autonomy_mean} km")
    print(f"Distance max grille traversée avec soc=0.10 : {0.10*autonomy_mean:.0f} km >> {c.C_GRID/1e3:.1f} km ✓")
