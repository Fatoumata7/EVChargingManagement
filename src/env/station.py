"""
station.py — Agent station de recharge
"""

import numpy as np
import random
from loguru import logger
from ortools.linear_solver import pywraplp

import src.env.utils as utils
import src.env.offer as off
import src.experiments.config as config


class Station:

    def __init__(self, m: int, society_id: int, config: config.SimulationConfig,
                 spec: dict | None = None, rng=None):
        """
        Parameters
        ----------
        spec : dict | None
            Paramètres explicites (loc, nb_charg_spot, alpha) issus d'un
            `WorldSpec`. Si fourni, aucun tirage aléatoire n'a lieu ici : la
            station est reconstructible à l'identique pour chaque méthode
            comparée. Si None, comportement historique (tirage aléatoire).
        """
        self.m = m
        self.society_id = society_id
        self.config = config

        if spec is not None:
            self.loc = np.asarray(spec['loc'], dtype=float)
            self.nb_charg_spot = int(spec['nb_charg_spot'])
            self.alpha = float(spec['alpha'])
        else:
            self.loc = utils.init_pos(config, rng=rng)
            self.nb_charg_spot = random.randint(
                config.NB_CHARG_SPOT['low'], config.NB_CHARG_SPOT['high'])
            self.alpha = random.uniform(0.1, 0.9)  # poids profit vs risque

        self.strategy = None   # injecté par Society.add_station()
        self.alpha_save = [self.alpha]

        # --- drapeaux de méthode (cf. src/experiments/methods.py)
        # Valeurs par défaut = BRAM-EV. `Simulation` les surcharge à
        # l'initialisation, une fois la méthode connue : le monde tiré reste
        # identique d'une méthode à l'autre, seule sa lecture change.
        self.score_index = society_id    # indice lu dans `car.score`
        self.score_weighting = 'duration'  # 'duration' | 'event'

        self.T = config.TOTAL_TIME
        self.schedule = np.full((self.nb_charg_spot, self.T), -1, dtype=int)

        # Version du calendrier par borne : incrémentée à chaque écriture.
        # Une offre porte la version vue à l'émission ; un écart signale que le
        # calendrier a bougé entre l'offre et la confirmation.
        self.charger_version = np.zeros(self.nb_charg_spot, dtype=int)
        self._offer_counter = 0

        # --- count metrics
        self.nb_pres = 0
        self.nb_no_show = 0
        self.nb_early_canc = 0
        self.nb_late_canc = 0
        self.nb_reservations = 0

        self.nb_rejected_request = 0
        self.nb_request = 0

        # --- occupation cumulée
        # `schedule` est un état *courant* : chaque fin de session ou annulation
        # y remet les slots à -1. Le lire en fin de run donnait donc un taux
        # d'occupation nul pour toutes les méthodes. Ces deux compteurs sont
        # cumulatifs et survivent aux libérations.
        self.nb_slots_reserved = 0   # slots-bornes écrits au calendrier
        self.nb_slots_served = 0     # slots-bornes réellement utilisés en charge

        # --- réservations closes par un événement exogène
        self.nb_breakdown_canc = 0   # véhicule tombé en panne avant la session
        self.nb_unresolved = 0       # réservation encore ouverte à la fin de l'horizon

        # --- sécurisation des offres
        self.nb_offer_issued = 0     # offres émises
        self.nb_offer_expired = 0    # offres non retenues par le véhicule / TTL dépassé
        self.nb_confirm_refused = 0  # confirmations refusées à la revalidation
        self.nb_stale_confirm = 0    # confirmations acceptées malgré une version périmée

    # ------------------------------------------------------------------
    # Méthode
    # ------------------------------------------------------------------

    def apply_method(self, spec, config=None):
        """
        Applique les drapeaux d'une `MethodSpec` à cette station.

        Trois mécanismes internes sont concernés :

        * `reputation_scope` — `'society'` : chaque société tient son propre
          score (le score est un actif local à un opérateur) ; `'global'` :
          toutes les stations lisent et écrivent la case 0, la réputation
          devient un bien public partagé.
        * `score_weighting` — `'duration'` : la pénalité est proportionnelle à
          la durée réservée ; `'event'` : pénalité forfaitaire par événement.
        * `alpha_mode` — `'fixed'` : l'arbitrage profit/risque est le même pour
          toutes les stations (`config.ALPHA_FIXED`), ce qui neutralise
          l'hétérogénéité initiale des alpha.

        Appelée par `Simulation.__init__` : le `WorldSpec` reste la source de
        vérité du monde, la méthode n'en change que la lecture.
        """
        self.score_index = 0 if spec.reputation_scope == 'global' else self.society_id
        self.score_weighting = spec.score_weighting

        if spec.alpha_mode == 'fixed':
            alpha = float(getattr(config or self.config, 'ALPHA_FIXED', 0.5))
            self.alpha = alpha
            # `alpha_save[0]` documente l'alpha effectivement utilisé : la table
            # alpha resterait sinon celle du monde, pas celle de la méthode.
            self.alpha_save = [alpha]

    # ------------------------------------------------------------------
    # Score
    # ------------------------------------------------------------------

    def update_car_score(self, car_agent, status, d_n):
        """
        Met à jour la composante f du score du véhicule.

        Le poids de l'événement est la durée réservée (`score_weighting =
        'duration'`, défaut : un no-show de 2 h coûte plus qu'un no-show de
        20 min) ou 1 (`'event'` : pénalité forfaitaire).
        """
        mu = self.strategy
        weight = float(d_n) if self.score_weighting == 'duration' else 1.0
        if status == 'pres':
            delta = +mu['pres'] * weight
        elif status == 'early':
            delta = -mu['early'] * weight
        elif status == 'late':
            delta = -mu['late'] * weight
        else:  # 'abs'
            delta = -mu['abs'] * weight
        car_agent.score[self.score_index] += delta

    # ------------------------------------------------------------------
    # Optimisation ILP
    # ------------------------------------------------------------------

    def process_demands(self, station_demands, t_c):
        """
        Résout le problème d'allocation et retourne une liste de (Car, Offer).

        Contiguïté
        ----------
        Le modèle impose que les slots alloués à une demande forment **un seul
        bloc contigu sur une seule borne**. C'est obtenu par une variable de
        front montant `s[n,j,t]` (« la recharge de n démarre en t sur j ») avec
        au plus un front montant par demande :

            s[n,j,t] >= a[n,j,t] - a[n,j,t-1]      (a absent => 0)
            sum_{j,t} s[n,j,t] <= 1

        La durée reste variable (offre partielle autorisée, <= d_n), mais
        `[t_arr, t_dep)` couvre désormais exactement `d_prop` slots : l'offre
        ne peut plus être un intervalle reconstruit à partir de slots disjoints.
        """
        if not station_demands:
            return []

        solver = pywraplp.Solver.CreateSolver("SCIP")
        solver.SetTimeLimit(60000 * 5) # 60000 -> 1 min

        T = self.T
        n_list, cars = [], []
        t_hat_arr, t_hat_dep = {}, {}
        scores, distance, d_n, g_n = {}, {}, {}, {}
        self.nb_request += len(station_demands)

        for car, req in station_demands:
            n = req['n']
            n_list.append(n)
            cars.append(car)

            x_n, y_n = req['loc']
            x_m, y_m = self.loc
            dist = np.sqrt((x_m - x_n) ** 2 + (y_m - y_n) ** 2)
            distance[n] = dist

            # Créneau nominal = émission + horizon de planification + trajet.
            # `t_max_n`, la fenêtre de `a[n,j,t]` et la pénalité `D` de
            # l'objectif sont tous définis relativement à `t_hat_arr` : ils
            # suivent le décalage sans modification.
            arr = utils.nominal_arrival(req['t_n'], req.get('l_n', 0),
                                        dist, self.config)
            t_hat_arr[n] = arr
            t_hat_dep[n] = arr + req['d_n']
            d_n[n] = req['d_n']
            g_n[n] = req['g_n']
            scores[n] = float(car.score[self.score_index])

        # Variables de décision : a[n,j,t] = 1 si n occupe la borne j au slot t
        a = {}
        for n in n_list:
            t_max_n = min(T, int(t_hat_arr[n] + g_n[n] + d_n[n]) + 1)
            for j in range(self.nb_charg_spot):
                for t in range(max(t_c, t_hat_arr[n]), t_max_n):
                    if self.schedule[j, t] == -1:
                        a[n, j, t] = solver.BoolVar(f"a_{n}_{j}_{t}")

        y = {}
        for n in n_list:
            for j in range(self.nb_charg_spot):
                y[n, j] = solver.BoolVar(f"y_{n}_{j}")

        # Contrainte : un seul chargeur par demande
        for n in n_list:
            solver.Add(solver.Sum(y[n, j] for j in range(self.nb_charg_spot)) <= 1)

        for (n, j, t), var in a.items():
            solver.Add(var <= y[n, j])

        # Contrainte capacité
        for j in range(self.nb_charg_spot):
            for t in range(t_c, T):
                solver.Add(
                    solver.Sum(a[n, j, t] for n in n_list if (n, j, t) in a) <= 1
                )

        # Contrainte durée (<= d_n, pas = pour permettre offres partielles)
        for n in n_list:
            solver.Add(
                solver.Sum(
                    a[n, j, t]
                    for j in range(self.nb_charg_spot)
                    for t in range(T)
                    if (n, j, t) in a
                ) <= d_n[n]
            )

        # Contrainte de contiguïté : au plus un front montant par demande.
        # Un slot absent de `a` (borne déjà occupée, ou hors fenêtre) vaut 0,
        # donc reprendre après un trou compterait un second front montant.
        s_start = {}
        for (n, j, t) in a:
            s_start[n, j, t] = solver.BoolVar(f"s_{n}_{j}_{t}")
            prev = a.get((n, j, t - 1))
            if prev is None:
                solver.Add(s_start[n, j, t] >= a[n, j, t])
            else:
                solver.Add(s_start[n, j, t] >= a[n, j, t] - prev)

        for n in n_list:
            starts = [var for (nn, j, t), var in s_start.items() if nn == n]
            if starts:
                solver.Add(solver.Sum(starts) <= 1)

        # Objectif agrégé
        objective = solver.Objective()
        for (n, j, t), var in a.items():
            if t < t_hat_arr[n]:
                D = t_hat_arr[n] - t
            elif t > t_hat_dep[n]:
                D = t - t_hat_dep[n]
            else:
                D = 0
            profit  = self.config.w1 * self.config.z
            penalty = self.config.w2 * D
            risk    = scores[n]
            coef = self.alpha * (profit - penalty) + (1 - self.alpha) * risk
            objective.SetCoefficient(var, coef)
        objective.SetMaximization()

        status = solver.Solve()

        offers = []
        if status not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
            return offers

        for idx, n in enumerate(n_list):
            j_selected = next(
                (j for j in range(self.nb_charg_spot) if y[n, j].solution_value() > 0.5),
                None
            )
            if j_selected is None:
                self.nb_rejected_request += 1
                continue

            times = sorted(t for (nn, j, t), var in a.items()
                           if nn == n and j == j_selected and var.solution_value() > 0.5)
            if not times:
                # demande qui n'a pas pu être satisfaite
                self.nb_rejected_request += 1
                continue

            t_arr, t_dep = times[0], times[-1] + 1
            # Garantie apportée par la contrainte de contiguïté
            assert t_dep - t_arr == len(times), (
                f"Station {self.m}: créneaux non contigus pour la demande {n} "
                f"({times})"
            )
            assert np.all(self.schedule[j_selected, t_arr:t_dep] == -1), (
                f"Station {self.m}: créneaux déjà réservés proposés à {n}"
            )

            offers.append((cars[idx], self._make_offer(
                charger_id=j_selected,
                t_arr=t_arr,
                t_dep=t_dep,
                d_prop=len(times),
                distance=distance[n],
                t_c=t_c
            )))

        return offers

    def _make_offer(self, charger_id, t_arr, t_dep, d_prop, distance, t_c):
        """Émet une offre horodatée, versionnée et à durée de validité limitée."""
        self._offer_counter += 1
        self.nb_offer_issued += 1
        return off.Offer(
            station_id=self.m,
            charger_id=charger_id,
            t_arr=t_arr,
            t_dep=t_dep,
            d_prop=d_prop,
            distance=distance,
            offer_id=f"s{self.m}-o{self._offer_counter:06d}",
            t_issued=t_c,
            t_expire=t_c + self.config.OFFER_TTL_SLOTS,
            charger_version=int(self.charger_version[charger_id])
        )

    # ------------------------------------------------------------------
    # Réservation & planning
    # ------------------------------------------------------------------

    def validate_offer(self, offer, t_c=None):
        """
        Revalide une offre au moment de la confirmation.

        Returns
        -------
        (ok, reason) : (bool, str | None)

        La vérification faisant autorité est l'état réel du calendrier : une
        offre dont la version de borne a changé reste confirmable si ses slots
        sont toujours libres (cas normal : une autre borne, ou un autre
        intervalle de la même borne, a été réservé entre-temps). Le décalage de
        version est alors compté (`nb_stale_confirm`) et non refusé.
        """
        if offer.station_id != self.m:
            return False, 'wrong_station'
        if not offer.is_pending():
            return False, f'status_{offer.status.lower()}'
        if t_c is not None and offer.is_expired(t_c):
            return False, 'expired'
        if not offer.is_contiguous():
            return False, 'not_contiguous'

        j = offer.charger_id
        if not (0 <= j < self.nb_charg_spot):
            return False, 'unknown_charger'

        t_start = offer.t_arr
        t_end = min(offer.t_dep, self.T)
        if t_start >= self.T or t_end <= t_start:
            return False, 'out_of_horizon'
        if t_c is not None and t_start < t_c:
            return False, 'slot_in_the_past'

        if not np.all(self.schedule[j, t_start:t_end] == -1):
            return False, 'slot_taken'

        return True, None

    def confirm_reservation(self, car_id, offer, t_c=None):
        """
        Confirme une offre après revalidation.

        Returns
        -------
        bool
            True si la réservation est inscrite au calendrier. False si l'offre
            a été refusée (elle passe alors en statut REJECTED et ne peut plus
            être confirmée).
        """
        ok, reason = self.validate_offer(offer, t_c)
        if not ok:
            offer.reject(reason)
            self.nb_confirm_refused += 1
            return False

        j = offer.charger_id
        if offer.charger_version != int(self.charger_version[j]):
            self.nb_stale_confirm += 1

        t_start = offer.t_arr
        t_end = min(offer.t_dep, self.T)
        self.schedule[j, t_start:t_end] = car_id
        self.charger_version[j] += 1

        offer.confirm()
        self.nb_reservations += 1
        self.nb_slots_reserved += int(t_end - t_start)
        return True

    def record_served_slot(self) -> None:
        """Comptabilise un slot-borne effectivement passé en charge.

        Appelé par la boucle de simulation à chaque slot de recharge active.
        L'écart avec `nb_slots_reserved` est exactement ce que les no-shows et
        les annulations tardives coûtent à la station : des slots bloqués puis
        jamais utilisés.
        """
        self.nb_slots_served += 1

    def expire_offer(self, offer):
        """Fait expirer une offre non retenue (elle ne sera jamais confirmable)."""
        if offer.is_pending():
            offer.expire()
            self.nb_offer_expired += 1

    def release_reservation(self, car_id, offer):
        """Libère les créneaux réservés (pour annulation ou fin de session)."""
        j = offer.charger_id
        mask = self.schedule[j, :] == car_id
        if np.any(mask):
            self.schedule[j, mask] = -1
            self.charger_version[j] += 1

    def get_current_charger_and_slot(self, car_id, t_c):
        """Retourne (j, True) si le véhicule doit être en charge à t_c."""
        for j in range(self.nb_charg_spot):
            if 0 <= t_c < self.T and self.schedule[j, t_c] == car_id:
                return j, True
        return None, False

    def is_session_finished(self, car_id, t_c):
        """Retourne True si le véhicule n'a plus de créneaux à partir de t_c."""
        for j in range(self.nb_charg_spot):
            if np.any(self.schedule[j, t_c:] == car_id):
                return False
        return True

    def total_nb_allocated_slot(self):
        return int(np.sum(self.schedule != -1))

    def slot_capacity(self) -> int:
        """Nombre total de slots-bornes offerts sur l'horizon."""
        return int(self.nb_charg_spot * self.T)

    def outcomes_report(self) -> dict:
        """Issues des réservations confirmées + santé du protocole d'offre."""
        capacity = max(1, self.slot_capacity())
        return {
            'station_id':          self.m,
            'society_id':          self.society_id,
            'nb_charg_spot':       self.nb_charg_spot,
            'alpha':               round(float(self.alpha), 4),
            'score_index':         self.score_index,
            'score_weighting':     self.score_weighting,
            'nb_request':          self.nb_request,
            'nb_rejected_request': self.nb_rejected_request,
            'nb_offer_issued':     self.nb_offer_issued,
            'nb_offer_expired':    self.nb_offer_expired,
            'nb_confirm_refused':  self.nb_confirm_refused,
            'nb_stale_confirm':    self.nb_stale_confirm,
            'nb_reservations':     self.nb_reservations,
            'nb_pres':             self.nb_pres,
            'nb_no_show':          self.nb_no_show,
            'nb_early_canc':       self.nb_early_canc,
            'nb_late_canc':        self.nb_late_canc,
            'nb_breakdown_canc':   self.nb_breakdown_canc,
            'nb_unresolved':       self.nb_unresolved,
            'nb_slots_reserved':   self.nb_slots_reserved,
            'nb_slots_served':     self.nb_slots_served,
            # Part de la capacité de l'horizon réservée / réellement utilisée.
            # Leur écart chiffre les slots bloqués puis perdus.
            'occupancy_rate':      round(self.nb_slots_reserved / capacity, 4),
            'service_rate':        round(self.nb_slots_served / capacity, 4),
        }

    def display_parameters(self, file):
        print('--- AGENT STATION', file=file)
        print(f'  m             : {self.m}', file=file)
        print(f'  loc           : {self.loc}', file=file)
        print(f'  society_id    : {self.society_id}', file=file)
        print(f'  nb_charg_spot : {self.nb_charg_spot}', file=file)
        print(f'  alpha         : {self.alpha:.3f}', file=file)
        print(f'  strategy      : {self.strategy}', file=file)
        print(f'  schedule shape: {self.schedule.shape}', file=file)
