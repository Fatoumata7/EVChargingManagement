"""
car.py — Agent véhicule électrique
"""

import numpy as np
import random
from collections import deque

import src.env.utils as utils
import src.experiments.config as config


#: Critères de sélection d'une offre par le véhicule. `methods.py` en est
#: la source de vérité (`OFFER_CHOICES`) ; ce tuple doit rester aligné.
OFFER_CRITERIA = ('utility', 'nearest', 'waiting', 'load', 'random')


class Car:

    def __init__(self, idx: int, nb_society: int, config: config.SimulationConfig,
                 spec: dict | None = None, rng_hub=None):
        """
        Parameters
        ----------
        spec : dict | None
            Paramètres explicites issus d'un `WorldSpec` (position, SoC,
            autonomie, seuil, theta, préférences, puissance). Si fourni, aucun
            tirage n'a lieu ici : le véhicule est reconstructible à l'identique
            pour chaque méthode comparée.
        rng_hub : RngHub | None
            Fabrique de flux aléatoires. Fournit quatre flux indépendants pour
            ce véhicule (déplacement / comportement / requête / horizon de
            planification), ce qui permet de comparer deux méthodes sur le
            *même* aléa : la divergence des décisions ne décale pas les tirages
            des autres usages.
        """

        self.config = config
        self.idx = idx

        # ---- Flux aléatoires dédiés (reproductibilité + common random numbers)
        if rng_hub is not None:
            self.rng_move     = rng_hub.stream('car_move', idx)
            self.rng_behavior = rng_hub.stream('car_behavior', idx)
            self.rng_request  = rng_hub.stream('car_request', idx)
            self.rng_lead     = rng_hub.stream('car_lead', idx)
            self.rng_choice   = rng_hub.stream('car_choice', idx)
        else:
            self.rng_move     = np.random.default_rng()
            self.rng_behavior = np.random.default_rng()
            self.rng_request  = np.random.default_rng()
            self.rng_lead     = np.random.default_rng()
            self.rng_choice   = np.random.default_rng()

        if spec is not None:
            self.loc = np.asarray(spec['loc'], dtype=float)
            self.soc_init        = float(spec['soc_init'])
            self.autonomy        = float(spec['autonomy'])
            self.theta           = dict(spec['theta'])
            self.pref            = dict(spec['pref'])
            self.charging_power  = int(spec['charging_power'])
            self.soc_threshold_m = float(spec['soc_threshold_m'])
        else:
            self.loc = utils.init_pos(config)
            self.soc_init        = self.init_soc()
            self.autonomy        = self.define_autonomy()
            self.theta           = self.generate_cancel_probabilities()
            self.pref            = self.generate_preferences()
            self.charging_power  = self.generate_charging_power()        # km/slot
            self.soc_threshold_m = utils.get_truncated_normal(
                mean=self.config.CAR_SOC_THRESHOLD_PARAMS['mean'],
                sd=self.config.CAR_SOC_THRESHOLD_PARAMS['sd'],
                low=self.config.CAR_SOC_THRESHOLD_PARAMS['low'],
                high=self.config.CAR_SOC_THRESHOLD_PARAMS['high']) * self.autonomy

        self.x, self.y = float(self.loc[0]), float(self.loc[1])
        self.soc_m = self.autonomy * self.soc_init # distance restante à parcourir avec état actuel de la batterie
        # 'DRIVING', 'REQUESTING', 'DRIVING_TO_STATION', 'AT_STATION',
        # 'CHARGING', 'WAITING', 'BREAKDOWN', 'PARKED_SEARCHING',
        # 'PARKED_NO_SHOW' (cf. PARKED_STATES)
        self.state = 'DRIVING'
        self.request = None
        self.reservation = None
        self.behavior = None
        self.speed_to_station = None

        # ---- Suivi de l'intention d'annulation (cf. Simulation._process_cancellations)
        self.cancel_intent    = None   # comportement tiré à la réservation
        self.reservation_slot = None   # slot d'émission de la requête réservée
        self.reservation_lead = None   # nb de slots entre requête et arrivée prévue

        # ---- Réputation : score borné sur une fenêtre glissante
        # `score[j]` est *dérivé* de `score_history[j]` — ne jamais l'écrire
        # directement, passer par `record_score_event` (ou `reset_score`).
        self.score = np.zeros(nb_society)
        self.score_history = [deque(maxlen=config.SCORE_MEMORY)
                              for _ in range(nb_society)]
        self.u_total = 0.0
        self.nb_sessions = 0
        self.nb_rejected = 0
        self.nb_request = 0
        self.nb_offers_received = 0
        self.nb_confirm_failed = 0

        # ---- Relance de recherche (cf. Simulation, état PARKED_SEARCHING)
        self.search_retries = 0    # relances consommées pour la demande courante

        self.schedule_requested = np.zeros(config.TOTAL_TIME)

    def init_soc(self):
        return random.uniform(self.config.CAR_INIT_SOC['low'],
                              self.config.CAR_INIT_SOC['high'])

    #: États où le véhicule est à l'arrêt : il ne se déplace pas, donc ne
    #: consomme rien. Aucune phase de `Simulation.step` ne les déplace.
    PARKED_STATES = frozenset({'PARKED_NO_SHOW', 'PARKED_SEARCHING'})

    def set_state(self, new_state):
        valid = {'WAITING', 'DRIVING', 'CHARGING', 'REQUESTING',
                 'DRIVING_TO_STATION', 'AT_STATION', 'BREAKDOWN'} | self.PARKED_STATES
        assert new_state in valid, f"État inconnu : {new_state}"
        self.state = new_state

    def set_reservation(self, best_offer):
        self.reservation = best_offer

    def set_behavior(self, behavior):
        self.behavior = behavior

    def clear_reservation(self):
        """Remet à zéro tout l'état lié à une réservation close."""
        self.reservation = None
        self.request = None
        self.behavior = None
        self.cancel_intent = None
        self.reservation_slot = None
        self.reservation_lead = None
        self.search_retries = 0

    def define_autonomy(self):
        """
        Définir l'autonomy du véhicule (multiple de <scale> et en mètres)
        """
        scale = 5                   # pour forcer autonomy comme multiple de 5
        autonomy = utils.get_truncated_normal(
            mean=self.config.CAR_AUTONOMY_PARAMS_KM['mean'] / scale,
            sd=self.config.CAR_AUTONOMY_PARAMS_KM['sd'] / scale,
            low=self.config.CAR_AUTONOMY_PARAMS_KM['low'] / scale,
            high=self.config.CAR_AUTONOMY_PARAMS_KM['high'] / scale)
        return int(autonomy) * scale * 1e3

    def generate_cancel_probabilities(self, noise_range: float = 0.2):
        weights = {
            "pres":  self.config.BASE_CANCEL_PROB['pres'],
            "abs":   self.config.BASE_CANCEL_PROB['abs'],
            "early": self.config.BASE_CANCEL_PROB['early'],
            "late":  self.config.BASE_CANCEL_PROB['late']
        }
        noise_range = self.config.BASE_CANCEL_PROB['noise']
        weights_with_noise = {
            k: max(0.1, v + v * random.uniform(-noise_range, noise_range))
            for k, v in weights.items()
        }
        tot = sum(weights_with_noise.values())
        return {k: v / tot for k, v in weights_with_noise.items()}

    def generate_preferences(self):
        prefs = {k: random.uniform(0., 1.) for k in ('energy', 'dist', 'wait')}
        tot = sum(prefs.values())
        return {k: v / tot for k, v in prefs.items()}

    def generate_charging_power(self):
        return np.random.choice([i for i in range(4, 9)])  # km/slot

    def draw_behavior(self):
        """
        Tire le comportement réalisé pour la réservation en cours.

        Utilise le flux `car_behavior`, indépendant du déplacement : pour une
        même graine, la k-ième réservation d'un véhicule donné tire le même
        comportement quelle que soit la méthode d'allocation testée.
        """
        keys = list(self.theta.keys())
        probs = np.asarray([self.theta[k] for k in keys], dtype=float)
        probs = probs / probs.sum()
        return str(self.rng_behavior.choice(keys, p=probs))

    def generate_charging_duration_request(self, strategies):
        if self.soc_m >= self.autonomy * 0.95 :
            return 0
        weights   = [s[0] for s in strategies]
        intervals = [s[1] for s in strategies]
        idx_choice = self.rng_request.choice(len(intervals), p=weights)
        low, high = intervals[idx_choice]
        target_soc = self.rng_request.uniform(low, high) * self.autonomy   # en mètres
        if self.soc_m > target_soc:
            target_soc = self.autonomy
        needed_km = (target_soc - self.soc_m) * 1e-3                # en kilomètres
        return max(int(needed_km / self.charging_power) + 1, 1)

    def update_car_speed(self):
        if self.behavior == 'pres':
            reduce_factor = 1
        else:
            reduce_factor = float(self.rng_behavior.choice(self.config.REDUCE_SPEED_FACTORS))
        self.speed_to_station = self.config.CAR_SPEED / reduce_factor

    def update_state(self, loc=None):
        """
        Déplace la voiture d'un slot.
        Si loc est fourni, la voiture se dirige vers cette position.
        Retourne True si la voiture est arrivée à destination.
        ---
        Si soc <= SOC_BREAKDOWN_THRESHOLD et pas en route confirmée → BREAKDOWN.
        Retourne True si arrivée à destination, 'breakdown' si panne en route.
        """
        threshold_at_station = 10      # distance en mètres à partir de laquelle on considère que le véhicule est arrivé à la station
        # ── Garde panne ──────────────────────────────────────────────────
        if self.soc_m <= self.config.SOC_BREAKDOWN_THRESHOLD:
            if self.state == 'DRIVING':
                self.state = 'BREAKDOWN'
                return False
            # En route vers station : on laisse terminer le trajet (inertie)
            # mais on ne consomme plus (poussée à la main)
            if self.state == 'DRIVING_TO_STATION':
                # avance quand même mais sans consommer davantage
                if loc is not None:
                    x_m, y_m = loc
                    dx, dy = x_m - self.x, y_m - self.y
                    if abs(dx) < threshold_at_station and abs(dy) < threshold_at_station:
                        self.set_state('AT_STATION')
                        return True
                    step_size = self.speed_to_station * 0.5   # réduit (poussée)
                    move_axis = 'x' if abs(dx) >= abs(dy) else 'y'
                    if move_axis == 'x':
                        self.x = np.clip(self.x + np.sign(dx)*min(abs(dx),step_size), 0, self.config.C_GRID)
                    else:
                        self.y = np.clip(self.y + np.sign(dy)*min(abs(dy),step_size), 0, self.config.C_GRID)
                    if abs(self.x-x_m) < threshold_at_station and abs(self.y-y_m) < threshold_at_station:
                        self.set_state('AT_STATION')
                        return True
                return False
            return False

        x_init, y_init = self.x, self.y

        if loc is None:
            move_axis = self.rng_move.choice(['x', 'y'])
            step = self.rng_move.uniform(-1, 1) * self.config.CAR_SPEED
            if move_axis == 'x':
                self.x = np.clip(self.x + step, 0, self.config.C_GRID)
            else:
                self.y = np.clip(self.y + step, 0, self.config.C_GRID)
        else:
            x_m, y_m = loc
            dx, dy = x_m - self.x, y_m - self.y
            if abs(dx) < threshold_at_station and abs(dy) < threshold_at_station:
                self.set_state('AT_STATION')
                return True
            move_axis = 'x' if abs(dx) >= abs(dy) else 'y'
            step_size = self.rng_move.uniform(0, self.speed_to_station)
            if move_axis == 'x':
                step = np.sign(dx) * min(abs(dx), step_size)
                self.x = np.clip(self.x + step, 0, self.config.C_GRID)
            else:
                step = np.sign(dy) * min(abs(dy), step_size)
                self.y = np.clip(self.y + step, 0, self.config.C_GRID)
            if abs(self.x - x_m) < threshold_at_station and abs(self.y - y_m) < threshold_at_station:
                self.set_state('AT_STATION')
                return True

        dist = abs(self.x - x_init) + abs(self.y - y_init)
        self.soc_m = max(0., self.soc_m - dist)

        # Vérifie panne après déplacement
        if self.soc_m <= self.config.SOC_BREAKDOWN_THRESHOLD and self.state == 'DRIVING':
            self.state = 'BREAKDOWN'

        return False

    def charge_one_slot(self):
        """Recharge la batterie d'un slot (appelé depuis Simulation)."""
        delta_soc = self.charging_power * 1e3
        self.soc_m = min(self.autonomy, self.soc_m + delta_soc)

    def needs_charging(self):
        # ne pas émettre de requête si déjà en panne.
        # `PARKED_SEARCHING` est admis : le véhicule s'est arrêté faute de
        # station ou d'offre et doit pouvoir relancer sa demande. Il ne
        # consomme pas entre-temps, donc son SoC — et donc `d_n` — reste valide.
        return (self.soc_m <= self.soc_threshold_m
                and self.state in ('DRIVING', 'PARKED_SEARCHING')
                and self.soc_m > self.config.SOC_BREAKDOWN_THRESHOLD)

    def draw_reservation_lead(self) -> int:
        """
        Horizon de planification de la requête courante, en slots.

        Le conducteur ne réserve pas systématiquement pour l'instant présent :
        il vise un créneau situé `l_n` slots plus tard. C'est ce délai qui rend
        l'annulation *anticipée* possible — sans lui, `t_arr = t_n` et toute
        annulation est mécaniquement tardive (cf. `utils.nominal_arrival` et
        `SimulationConfig.late_cancel_threshold`).

        Tiré sur `rng_lead`, un flux **dédié**. Le partager avec `rng_request`
        décalerait durée, rayon et patience de toutes les requêtes suivantes dès
        que l'horizon est activé : les deux bras de l'ablation ne différeraient
        plus seulement par l'horizon. Flux séparé = intervention propre, ce qui
        est la raison d'être de `seeding.STREAM_CODES`.
        """
        p = self.config.RESERVATION_LEAD_PARAMS
        return int(self.rng_lead.integers(p['low'], p['high'] + 1))

    def emit_request(self, current_time, loc_n, id_demand):
        charging_duration = self.generate_charging_duration_request(
            self.config.CHARGING_DURATION_PARAMS)
        x_n, y_n = loc_n
        max_waiting_time = int(self.rng_request.integers(6, 24))
        max_dist = self.soc_m
        min_ray = min(self.config.MIN_RAY_SEARCH, self.config.COEFF_MAX_DIST * max_dist)
        max_ray = max(self.config.MIN_RAY_SEARCH, self.config.COEFF_MAX_DIST * max_dist)
        r_n = min(self.rng_request.uniform(min_ray, max_ray), self.config.MAX_RAY_SEARCH)
        request = {
            'n':       id_demand,
            'car_idx': self.idx,
            't_n':     current_time,
            'd_n':     charging_duration,
            'loc':     (x_n, y_n),
            'r_n':     r_n,
            'g_n':     max_waiting_time,
            'l_n':     self.draw_reservation_lead()
        }
        self.request = request
        self.nb_request += 1
        return request

    # ------------------------------------------------------------------
    # Réputation
    # ------------------------------------------------------------------

    def record_score_event(self, index: int, signed_stake: float,
                           weight: float) -> float:
        """
        Enregistre l'issue d'une réservation et recalcule le score de réputation.

        Parameters
        ----------
        index : int
            Indice de lecture du score (société, ou 0 en portée globale).
        signed_stake : float
            Enjeu normalisé de l'issue, dans [-1, 1] : positif pour une
            présence, négatif sinon, rapporté au plus gros enjeu du barème de
            la société (cf. `Station.update_car_score`).
        weight : float
            Poids de l'événement — durée réservée (`score_weighting =
            'duration'`) ou 1 (`'event'`).

        Le score est la moyenne pondérée des enjeux de la fenêtre, **atténuée
        par le taux de remplissage** de celle-ci :

            score = (Σ enjeu_i · poids_i / Σ poids_i) · (n / SCORE_MEMORY)

        La fenêtre compte toujours `SCORE_MEMORY` places ; les places non encore
        occupées comptent pour « inconnu », c'est-à-dire 0. Le score reste donc
        borné dans [-1, 1] — c'est une moyenne de valeurs de [-1, 1], réduite
        d'un facteur <= 1.

        Trois propriétés en découlent, toutes voulues :

        * *Droit à l'oubli* — au-delà de `SCORE_MEMORY` réservations, les plus
          anciennes sortent de la fenêtre.
        * *Rédemption effective* — sans l'atténuation, une **seule** issue
          négative suffisait à atteindre le plancher (moyenne d'un unique
          événement). Le véhicule devenait inéligible partout, ne recevait donc
          plus aucune réservation, et sa fenêtre ne pouvait plus tourner : le
          droit à l'oubli était inopérant, mesuré à 0 rédemption sur 9 véhicules
          sanctionnés. Il faut désormais une dégradation *soutenue* pour
          approcher le plancher, et un véhicule mal noté continue d'être servi
          par les stations les moins averses au risque — donc de pouvoir
          remonter.
        * *Fiabilité, pas ancienneté* — c'est un taux, pas un cumul. Un
          véhicule qui a beaucoup roulé n'est plus mécaniquement mieux noté
          qu'un véhicule fiable mais peu actif. Et un véhicule sans passé (score
          0, « inconnu ») n'est plus confondu avec un véhicule au bilan
          exactement équilibré.

        Le poids n'agit plus que *relativement*, à l'intérieur de la fenêtre :
        une réservation longue pèse plus qu'une courte dans la moyenne, mais une
        fenêtre d'événements de même durée donne le même score quelle que soit
        cette durée. C'est la contrepartie du bornage.
        """
        hist = self.score_history[index]
        hist.append((float(signed_stake), max(0., float(weight))))

        total_w = sum(w for _, w in hist)
        if total_w > 0.:
            mean = sum(stake * w for stake, w in hist) / total_w
        else:
            # Poids tous nuls : on retombe sur la moyenne simple plutôt que de
            # perdre l'information.
            mean = sum(stake for stake, _ in hist) / len(hist)

        confidence = len(hist) / float(hist.maxlen)
        self.score[index] = float(np.clip(mean * confidence, -1., 1.))
        return self.score[index]

    def reset_score(self):
        """Remet à zéro score et historique (véhicule sans passé connu)."""
        self.score[:] = 0.
        for hist in self.score_history:
            hist.clear()

    def widen_search(self) -> bool:
        """
        Élargit le rayon de recherche pour relancer la demande courante.

        Retourne True si une relance reste possible, False si le budget
        `MAX_SEARCH_RETRIES` est épuisé — auquel cas l'appelant doit faire
        renoncer le véhicule plutôt que de le laisser garé indéfiniment.

        Le rayon élargi dépasse volontairement `MAX_RAY_SEARCH`, qui borne la
        recherche de routine : ici le véhicule est bloqué et cherche plus loin
        que d'habitude. Il reste borné par la diagonale de la grille.

        Ni `d_n`, ni `g_n`, ni `l_n` ne sont retirés au sort : c'est la *même*
        demande qui est relancée, et redessiner ces valeurs consommerait de
        l'aléa à un rythme dépendant de la méthode testée — les flux des
        véhicules divergeraient entre BRAM-EV et Greedy.
        """
        if self.request is None:
            return False
        if self.search_retries >= self.config.MAX_SEARCH_RETRIES:
            return False
        self.search_retries += 1
        widened = self.request['r_n'] * self.config.SEARCH_RADIUS_GROWTH
        self.request['r_n'] = float(min(widened, self.config.max_search_radius()))
        return True

    def reemit_request(self, current_time):
        """
        Relance la demande courante depuis la position actuelle.

        L'identifiant de demande est conservé : du point de vue de l'usager
        c'est un seul besoin de recharge, dont on mesure la latence de bout en
        bout. Seule la date d'émission avance, pour que le créneau nominal
        (`t_n + l_n + trajet`) et le déclencheur d'annulation anticipée
        (`t_c > reservation_slot`) restent cohérents avec le temps courant.

        Le véhicule étant à l'arrêt depuis la tentative précédente, sa position
        et son SoC n'ont pas changé : `d_n` reste valide.
        """
        if self.request is None:
            raise RuntimeError("reemit_request sans requête en cours")
        self.request['t_n'] = current_time
        self.request['loc'] = (self.x, self.y)
        self.nb_request += 1
        return self.request

    def give_up_search(self):
        """Abandon après épuisement du budget de relances : le véhicule repart."""
        self.request = None
        self.search_retries = 0
        self.set_state('DRIVING')

    def update_schedule_requested(self, min_dist):
        """FIX : == → = (affectation)"""
        t_arr = utils.nominal_arrival(self.request['t_n'],
                                      self.request.get('l_n', 0),
                                      min_dist, self.config)
        t_dep = int(t_arr + self.request['d_n'])
        t_arr = min(t_arr, self.config.TOTAL_TIME - 1)
        t_dep = min(t_dep, self.config.TOTAL_TIME)
        self.schedule_requested[t_arr:t_dep] = 1

    def compute_utility(self, offer, request, min_dist):
        """
        FIX : parenthèse de normalisation distance corrigée.
        Signature alignée avec choose_offer (min_dist en paramètre).
        """
        d_n = request['d_n']
        if d_n <= 1:
            return 1.0   # impossible d'avoir maxEnergyDif = 0
        r_n = request['r_n']
        g_n = request['g_n']
        # L'horizon de planification `l_n` doit entrer ici : sans lui, le délai
        # voulu par le conducteur serait compté comme de l'attente subie,
        # `waitingTime / maxWaitingTime` dépasserait 1 et le `max(0., u)` final
        # écraserait *toutes* les utilités à zéro — le classement des offres
        # deviendrait arbitraire, sans erreur ni avertissement.
        t_hat_arr = utils.nominal_arrival(request['t_n'], request.get('l_n', 0),
                                          offer.distance, self.config)

        energyDif    = d_n - offer.d_prop
        maxEnergyDif = d_n - 1

        distance    = offer.distance
        maxDistance = r_n
        minDistance = min_dist

        waitingTime    = max(0, offer.t_arr - t_hat_arr)
        maxWaitingTime = g_n if g_n > 0 else 1

        # Normalisation distance : (d - dmin) / (dmax - dmin)
        dist_range = maxDistance - minDistance
        norm_dist = (distance - minDistance) / dist_range if dist_range > 0 else 0.

        u = (1.
             - self.pref['energy'] * (energyDif / maxEnergyDif)
             - self.pref['dist']   * norm_dist
             - self.pref['wait']   * (waitingTime / maxWaitingTime))
        return max(0., u)

    def rank_offers(self, offers, request, min_dist, criterion='utility'):
        """
        Classe les offres, la meilleure en tête.

        Le véhicule tente de confirmer dans cet ordre : si la station refuse la
        confirmation (offre périmée ou créneau plus libre), il se rabat sur
        l'offre suivante au lieu de renoncer.

        Parameters
        ----------
        criterion : {'utility', 'nearest', 'waiting', 'load', 'random'}
            `'utility'` — utilité multicritère décroissante (défaut, BRAM-EV).
            `'nearest'` — distance croissante : la variante
            `bramev_nearest_offer` de l'étude d'ablation, qui mesure ce que
            l'arbitrage énergie/distance/attente apporte réellement.
            `'waiting'` — attente croissante (baseline `min_waiting`).
            `'load'` — taux d'occupation futur croissant (baseline `load_aware`).
            `'random'` — tirage uniforme parmi les offres reçues (baseline
            `random_feasible`). Toute offre reçue est faisable par
            construction : la station l'a produite depuis son propre calendrier
            et la revalide à la confirmation.

        L'utilité est calculée dans tous les cas : elle reste la mesure de
        satisfaction reportée (`car.u_total`), même quand elle ne pilote pas
        le choix.

        Les départages sont explicites et déterministes (utilité, puis
        identifiant de station) : deux exécutions du même monde classent à
        l'identique. Le critère `'random'` tire sur `rng_choice`, un flux dédié,
        pour ne pas décaler les autres tirages du véhicule.
        """
        if criterion not in OFFER_CRITERIA:
            raise ValueError(
                f"Critère de sélection inconnu : {criterion!r}. "
                f"Attendu parmi {list(OFFER_CRITERIA)}."
            )
        scored = [(offer, self.compute_utility(offer, request, min_dist))
                  for offer in offers]

        if criterion == 'nearest':
            scored.sort(key=lambda pair: (pair[0].distance, -pair[1],
                                          pair[0].station_id))
        elif criterion == 'waiting':
            scored.sort(key=lambda pair: (self._waiting_slots(pair[0], request),
                                          -pair[1], pair[0].station_id))
        elif criterion == 'load':
            scored.sort(key=lambda pair: (pair[0].station_load, -pair[1],
                                          pair[0].station_id))
        elif criterion == 'random':
            # Ordre canonique d'abord : la permutation ne doit pas dépendre de
            # l'ordre d'arrivée des offres, qui suit celui des stations.
            scored.sort(key=lambda pair: pair[0].station_id)
            order = self.rng_choice.permutation(len(scored))
            scored = [scored[i] for i in order]
        else:
            scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored

    def _waiting_slots(self, offer, request) -> int:
        """Attente subie : écart entre le créneau proposé et le créneau visé."""
        t_hat_arr = utils.nominal_arrival(request['t_n'], request.get('l_n', 0),
                                          offer.distance, self.config)
        return max(0, offer.t_arr - t_hat_arr)

    def choose_offer(self, offers, request, min_dist, criterion='utility'):
        ranked = self.rank_offers(offers, request, min_dist, criterion)
        if not ranked:
            return None, -np.inf
        return ranked[0]

    def display_parameters(self, file):
        print('--- AGENT CAR', file=file)
        print(f'  idx           : {self.idx}', file=file)
        print(f'  loc           : ({self.x:.1f}, {self.y:.1f})', file=file)
        print(f'  soc           : {self.soc_m * 1e-3:.3f}km', file=file)
        print(f'  soc threshold : {self.soc_threshold_m * 1e-3:.3f}km', file=file)
        print(f'  autonomy      : {self.autonomy * 1e-3}km', file=file)
        print(f'  state         : {self.state}', file=file)
        print(f'  theta         : {self.theta}', file=file)
        print(f'  pref          : {self.pref}', file=file)
        print(f'  charging_power: {self.charging_power} km/slot', file=file)
        print(f'  score         : {self.score}', file=file)
        print(f'  u_total       : {self.u_total:.4f}', file=file)
        print(f'  nb_sessions   : {self.nb_sessions}', file=file)
