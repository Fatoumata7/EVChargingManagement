"""
config.py — Paramètres de simulation (réalistes)
"""
import numpy as np


class SimulationConfig:

    # ------------------------------------------------------------------ GRILLE
    # 3×3 km : taille raisonnable pour une zone urbaine dense.
    C_GRID = 3 * 1e3            # 9 km^2 (1/10e de Paris)

    # ------------------------------------------------------------------ TEMPS
    SLOT_DURATION = 5               # 5 minutes, doit être multiple de 60
    NB_SLOTS_IN_ONE_HOUR = 12       # 60 / SLOT_DURATION

    # ------------------------------------------------------------------ VISUALIZATION
    VIS_DELAY = 1

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

    LATE_CANCEL_REF = 12    # annulation tardive si < 1h = 12 slots

    # Consommation énergétique : 10 kWh / 100 km
    ENERGY_CONSUMPTION = {
        'quantity_kW':     10,          # kWh (5)
        'distance_unit_m': 100 * 1e3    # 100 km en mètres (1000e3)
    }

    # ------------------------------------------------------------------ PANNE
    # Seuil en dessous duquel la voiture est considérée en panne (soc ≈ 0)
    SOC_BREAKDOWN_THRESHOLD = 3 * 1e3   # 1% → ~3 km restants

    # ------------------------------------------------------------------ SCÉNARIOS
    # Source unique de vérité pour les probabilités de comportement.
    # Les notebooks doivent appeler `set_scenario(nom)` au lieu de redéfinir
    # BASE_CANCEL_PROB localement (c'est ce qui avait produit des jeux de
    # paramètres divergents entre notebooks et rapport).
    #
    # Convention :
    #   pres  : se présente et honore la réservation
    #   abs   : no-show complet (créneau jamais libéré avant t_dep)
    #   early : annulation anticipée  (> LATE_CANCEL_REF slots avant l'arrivée)
    #   late  : annulation tardive    (<= LATE_CANCEL_REF slots avant l'arrivée)
    #
    # La sévérité croît de `optimistic` à `pessimistic` sur les deux dimensions
    # coûteuses pour l'opérateur (`abs` et `late`), et `noise` est identique
    # partout pour que les scénarios ne diffèrent que par les probabilités.
    SCENARIOS = {
        'optimistic':  {'pres': 75, 'abs': 10, 'early':  9, 'late':  6, 'noise': 0.15},
        'balance':     {'pres': 60, 'abs': 20, 'early': 12, 'late':  8, 'noise': 0.15},
        'pessimistic': {'pres': 40, 'abs': 25, 'early': 15, 'late': 20, 'noise': 0.15},
    }


    def __init__(self):

        self.TOTAL_TIME = 12 * 4 # 12 * 24 * 5        # 12 slots de 5min dans une heure, 4 heures

        # ------------------------------------------------------------------ REPRODUCTIBILITÉ
        # Graine unique de l'expérience. Fixée via set_seed() ; enregistrée avec
        # chaque résultat par le pipeline (src/pipeline).
        self.SEED = None
        self.SCENARIO_NAME = 'custom'      # renseigné par set_scenario()

        # ------------------------------------------------------------------ PROTOCOLE D'OFFRE
        # Durée de validité d'une offre, en slots. 1 = l'offre expire à la fin du
        # slot d'émission (une offre non confirmée immédiatement est perdue).
        self.OFFER_TTL_SLOTS = 1

        # Part du délai requête → arrivée en dessous de laquelle une annulation
        # est considérée tardive, quand ce délai est plus court que
        # LATE_CANCEL_REF (cf. late_cancel_threshold).
        self.LATE_CANCEL_FRACTION = 0.5

        # ------------------------------------------------------------------ HORIZON DE PLANIFICATION
        # Nombre de slots entre l'émission d'une requête et le créneau souhaité
        # (`request['l_n']`, tiré par requête dans `Car.emit_request`). Le
        # conducteur ne demande plus « charger maintenant » mais « charger dans
        # l_n slots » : le créneau nominal devient t_n + l_n + trajet
        # (cf. `utils.nominal_arrival`).
        #
        # Atteignabilité de l'annulation anticipée : elle se déclenche au plus
        # tôt en t_n + 1, donc slots_left = lead - 1, à comparer au seuil
        # late_cancel_threshold(lead). Il faut un délai effectif >= 3 slots
        # (cf. min_lead_for_early_cancel), et ce délai vaut l_n + ceil(trajet),
        # soit l_n + 1 sur cette grille : l_n >= 2 suffit donc ici. Au-delà de
        # 24, le gain est nul — la fenêtre ILP est plafonnée par la patience g_n.
        #
        # `low = 0` est délibéré : une partie des requêtes reste « je charge
        # maintenant » (conducteur déjà à court d'autonomie), ce qui conserve
        # dans chaque exécution un groupe témoin non anticipable et garde
        # observable la reclassification `early -> late`.
        #
        # {'low': 0, 'high': 0} désactive l'horizon : c'est le bras de contrôle
        # de l'ablation, celui où l'annulation anticipée est inatteignable.
        self.RESERVATION_LEAD_PARAMS = {'low': 12, 'high': 48}

        self.VISUALIZE = True

        self.NB_CARS       = 50
        self.NB_SOCIETIES  = 5
        self.NB_STATIONS   = 40

        self.w1 = 1.0    # poids profit dans l'objectif station
        self.w2 = 1.0    # poids pénalité éloignement temporel
        self.z  = 2.0    # constante de priorité profit (z > 1)

        # Valeur commune de alpha pour les méthodes dont `alpha_mode == 'fixed'`
        # (variante `bramev_fixed_alpha`, cf. src/experiments/methods.py).
        # Sans effet sur les autres méthodes, où alpha est tiré par station.
        self.ALPHA_FIXED = 0.5

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


    def set_seed(self, value: int) -> None:
        """
        Fixe la graine de l'expérience.

        Ne graine pas les générateurs : c'est `RngHub(seed)` (cf.
        src/experiments/seeding.py) qui le fait, appelé par `define_agents`.
        """
        if not isinstance(value, int):
            raise TypeError(
                f"SEED doit être un entier, reçu : {type(value).__name__}"
            )
        if value < 0:
            raise ValueError(f"SEED doit être >= 0, reçu : {value}")
        self.SEED = value


    def set_scenario(self, name: str) -> None:
        """
        Applique les probabilités de comportement d'un scénario nommé.

        Parameters
        ----------
        name : {'optimistic', 'balance', 'pessimistic'}
        """
        if name not in self.SCENARIOS:
            raise ValueError(
                f"Scénario inconnu : {name!r}. "
                f"Attendu parmi {sorted(self.SCENARIOS)}"
            )
        self.set_BASE_CANCEL_PROB(self.SCENARIOS[name])
        self.SCENARIO_NAME = name


    def set_ALPHA_FIXED(self, value: float) -> None:
        """
        Valeur commune de alpha imposée aux variantes à alpha fixe.

        Parameters
        ----------
        value : float
            Arbitrage profit/risque dans [0, 1]. Les alpha tirés par station le
            sont dans [0.1, 0.9] : rester dans cet intervalle garde la variante
            comparable au reste de la grille.
        """
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise TypeError(
                f"ALPHA_FIXED doit être un nombre, reçu : {type(value).__name__}"
            )
        if not 0. <= float(value) <= 1.:
            raise ValueError(f"ALPHA_FIXED doit être dans [0, 1], reçu : {value}")
        self.ALPHA_FIXED = float(value)

    def set_OFFER_TTL_SLOTS(self, value: int) -> None:

        if type(value) is not int:
            raise TypeError(
                f"OFFER_TTL_SLOTS doit être un int, reçu : {type(value).__name__}"
            )
        if value < 1:
            raise ValueError(f"OFFER_TTL_SLOTS doit être >= 1, reçu : {value}")
        self.OFFER_TTL_SLOTS = value


    def set_RESERVATION_LEAD_PARAMS(self, value: dict) -> None:
        """
        Bornes du tirage de l'horizon de planification, en slots.

        Parameters
        ----------
        value : dict
            `{'low': int, 'high': int}`, bornes inclusives avec 0 <= low <= high.
            `{'low': 0, 'high': 0}` reproduit le comportement historique
            (réservation pour le créneau immédiat).
        """
        if not isinstance(value, dict):
            raise TypeError(
                f"RESERVATION_LEAD_PARAMS doit être un dict, reçu : "
                f"{type(value).__name__}"
            )

        missing = {'low', 'high'} - set(value)
        if missing:
            raise ValueError(f"Clés manquantes : {missing}")

        low, high = value['low'], value['high']
        for name, v in (('low', low), ('high', high)):
            if not isinstance(v, int) or isinstance(v, bool):
                raise TypeError(
                    f"RESERVATION_LEAD_PARAMS['{name}'] doit être un int, "
                    f"reçu : {type(v).__name__}"
                )
            if v < 0:
                raise ValueError(
                    f"RESERVATION_LEAD_PARAMS['{name}'] doit être >= 0, reçu : {v}"
                )
        if low > high:
            raise ValueError(
                f"RESERVATION_LEAD_PARAMS : low ({low}) doit être <= high ({high})"
            )

        self.RESERVATION_LEAD_PARAMS = {'low': int(low), 'high': int(high)}


    def late_cancel_threshold(self, lead: int) -> int:
        """
        Seuil (en slots avant l'arrivée prévue) séparant annulation anticipée et
        annulation tardive, pour une réservation dont le délai requête → arrivée
        vaut `lead`.

        `LATE_CANCEL_REF` (2 h = 24 slots) suppose une réservation prise
        longtemps à l'avance. Ici le délai est souvent de quelques slots
        seulement (le trajet vers la station est court) : appliqué tel quel, le
        seuil absolu classait *toute* annulation comme tardive et rendait la
        branche « anticipée » inatteignable. Le seuil est donc borné par une
        fraction du délai réel, ce qui garantit que les deux régimes existent.
        """
        lead = max(0, int(lead))
        relative = int(lead * self.LATE_CANCEL_FRACTION)
        return max(1, min(self.LATE_CANCEL_REF, relative))


    def min_lead_for_early_cancel(self) -> int:
        """
        Plus petit délai requête → arrivée permettant une annulation *observée*
        comme anticipée.

        L'annulation anticipée se déclenche au plus tôt au slot suivant la
        réservation (`t_c = reservation_slot + 1`, cf.
        `Simulation._process_cancellations`), d'où `slots_left = lead - 1`.
        Elle n'est qualifiée `early` que si `slots_left > late_cancel_threshold(lead)`.
        En dessous de ce seuil, une intention `early` est nécessairement
        réalisée en `late` : la branche est inatteignable, ce qui était le
        comportement observé sur toute la grille (`reclassified` saturé à 100 %).

        Vaut 3 avec `LATE_CANCEL_FRACTION = 0.5`. Renvoie -1 si aucun délai ne
        convient (fraction trop proche de 1).

        Le délai effectif est `l_n + ceil(trajet)` : sur une grille où le trajet
        dure moins d'un slot il vaut `l_n + 1`, donc `l_n >= 2` suffit ici.
        """
        for lead in range(1, 3 * self.LATE_CANCEL_REF + 2):
            if lead - 1 > self.late_cancel_threshold(lead):
                return lead
        return -1


    def summary(self) -> dict:
        """
        Paramètres à enregistrer avec chaque résultat (traçabilité).
        """
        return {
            'seed':                  self.SEED,
            'scenario':              self.SCENARIO_NAME,
            'total_time':            self.TOTAL_TIME,
            'slot_duration_min':     self.SLOT_DURATION,
            'nb_cars':               self.NB_CARS,
            'nb_stations':           self.NB_STATIONS,
            'nb_societies':          self.NB_SOCIETIES,
            'nb_charg_spot':         dict(self.NB_CHARG_SPOT),
            'grid_m':                self.C_GRID,
            'car_speed_m_per_slot':  self.CAR_SPEED,
            'base_cancel_prob':      dict(self.BASE_CANCEL_PROB),
            'base_points_strategy':  dict(self.BASE_POINTS_STRATEGY),
            'strategy_noise':        self.STRATEGY_NOISE,
            'w1': self.w1, 'w2': self.w2, 'z': self.z,
            'gamma':                 self.GAMMA,
            'society_update_interval': self.SOCIETY_UPDATE_INTERVAL,
            'min_ray_search':        self.MIN_RAY_SEARCH,
            'max_ray_search':        self.MAX_RAY_SEARCH,
            'coeff_max_dist':        self.COEFF_MAX_DIST,
            'late_cancel_ref':       self.LATE_CANCEL_REF,
            'late_cancel_fraction':  self.LATE_CANCEL_FRACTION,
            'reservation_lead':      dict(self.RESERVATION_LEAD_PARAMS),
            'offer_ttl_slots':       self.OFFER_TTL_SLOTS,
            'alpha_fixed':           self.ALPHA_FIXED,
        }

    

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
