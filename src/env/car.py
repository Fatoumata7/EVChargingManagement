"""
car.py — Electric vehicle agent
"""

import numpy as np
import random
from collections import deque

import src.env.utils as utils
import src.experiments.config as config


#: Criteria a vehicle can use to select an offer. `methods.py` is the source of
#: truth (`OFFER_CHOICES`); this tuple must stay aligned with it.
OFFER_CRITERIA = ('utility', 'nearest', 'waiting', 'load', 'random')


class Car:

    def __init__(self, idx: int, nb_society: int, config: config.SimulationConfig,
                 spec: dict | None = None, rng_hub=None):
        """
        Parameters
        ----------
        spec : dict | None
            Explicit parameters coming from a `WorldSpec` (position, SoC,
            autonomy, threshold, theta, preferences, power). When provided, no
            random draw happens here: the vehicle is rebuilt identically for
            every method being compared.
        rng_hub : RngHub | None
            Random-stream factory. Provides independent streams for this vehicle
            (movement / behaviour / request / planning horizon / offer draw),
            which is what allows two methods to be compared on the *same*
            randomness: diverging decisions do not shift the draws of the other
            uses.
        """

        self.config = config
        self.idx = idx

        # ---- Dedicated random streams (reproducibility + common random numbers)
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
        self.soc_m = self.autonomy * self.soc_init # distance still drivable with the current battery level
        # 'DRIVING', 'REQUESTING', 'DRIVING_TO_STATION', 'AT_STATION',
        # 'CHARGING', 'WAITING', 'BREAKDOWN', 'PARKED_SEARCHING',
        # 'PARKED_NO_SHOW' (see PARKED_STATES)
        self.state = 'DRIVING'
        self.request = None
        self.reservation = None
        self.behavior = None
        self.speed_to_station = None

        # ---- Cancellation intent tracking (see Simulation._process_cancellations)
        self.cancel_intent    = None   # behaviour drawn at reservation time
        self.reservation_slot = None   # emission slot of the reserved request
        self.reservation_lead = None   # nb of slots between request and planned arrival

        # ---- Reputation: bounded score over a sliding window.
        # `score[j]` is *derived* from `score_history[j]` — never write it
        # directly, go through `record_score_event` (or `reset_score`).
        self.score = np.zeros(nb_society)
        self.score_history = [deque(maxlen=config.SCORE_MEMORY)
                              for _ in range(nb_society)]
        self.u_total = 0.0
        self.nb_sessions = 0
        self.nb_rejected = 0
        self.nb_request = 0
        self.nb_offers_received = 0
        self.nb_confirm_failed = 0

        # ---- Search retries (see Simulation, PARKED_SEARCHING state)
        self.search_retries = 0    # retries consumed by the current demand

        self.schedule_requested = np.zeros(config.TOTAL_TIME)

    def init_soc(self):
        return random.uniform(self.config.CAR_INIT_SOC['low'],
                              self.config.CAR_INIT_SOC['high'])

    #: States where the vehicle is stopped: it does not move, hence consumes
    #: nothing. No phase of `Simulation.step` moves a vehicle in these states.
    PARKED_STATES = frozenset({'PARKED_NO_SHOW', 'PARKED_SEARCHING'})

    def set_state(self, new_state):
        valid = {'WAITING', 'DRIVING', 'CHARGING', 'REQUESTING',
                 'DRIVING_TO_STATION', 'AT_STATION', 'BREAKDOWN'} | self.PARKED_STATES
        assert new_state in valid, f"Unknown state: {new_state}"
        self.state = new_state

    def set_reservation(self, best_offer):
        self.reservation = best_offer

    def set_behavior(self, behavior):
        self.behavior = behavior

    def clear_reservation(self):
        """Reset every piece of state tied to a closed reservation."""
        self.reservation = None
        self.request = None
        self.behavior = None
        self.cancel_intent = None
        self.reservation_slot = None
        self.reservation_lead = None
        self.search_retries = 0

    def define_autonomy(self):
        """
        Define the vehicle autonomy (multiple of <scale>, in meters).
        """
        scale = 5                   # forces autonomy to be a multiple of 5
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
        Draw the behaviour realised for the current reservation.

        Uses the `car_behavior` stream, independent from movement: for a given
        seed, the k-th reservation of a given vehicle draws the same behaviour
        whatever the allocation method under test.
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
        target_soc = self.rng_request.uniform(low, high) * self.autonomy   # in meters
        if self.soc_m > target_soc:
            target_soc = self.autonomy
        needed_km = (target_soc - self.soc_m) * 1e-3                # in kilometers
        return max(int(needed_km / self.charging_power) + 1, 1)

    def update_car_speed(self):
        if self.behavior == 'pres':
            reduce_factor = 1
        else:
            reduce_factor = float(self.rng_behavior.choice(self.config.REDUCE_SPEED_FACTORS))
        self.speed_to_station = self.config.CAR_SPEED / reduce_factor

    def update_state(self, loc=None):
        """
        Move the car by one slot.
        If `loc` is given, the car heads towards that position.
        Returns True if the car reached its destination.
        ---
        If soc <= SOC_BREAKDOWN_THRESHOLD and not on a confirmed trip → BREAKDOWN.
        Returns True on arrival, 'breakdown' if the car breaks down on the way.
        """
        threshold_at_station = 10      # distance in meters below which the vehicle counts as arrived at the station
        # ── Breakdown guard ──────────────────────────────────────────────
        if self.soc_m <= self.config.SOC_BREAKDOWN_THRESHOLD:
            if self.state == 'DRIVING':
                self.state = 'BREAKDOWN'
                return False
            # On the way to a station: the trip is allowed to finish (inertia)
            # but nothing is consumed any more (pushed by hand)
            if self.state == 'DRIVING_TO_STATION':
                # keep moving, without consuming further
                if loc is not None:
                    x_m, y_m = loc
                    dx, dy = x_m - self.x, y_m - self.y
                    if abs(dx) < threshold_at_station and abs(dy) < threshold_at_station:
                        self.set_state('AT_STATION')
                        return True
                    step_size = self.speed_to_station * 0.5   # reduced (pushed)
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

        # Check for a breakdown after moving
        if self.soc_m <= self.config.SOC_BREAKDOWN_THRESHOLD and self.state == 'DRIVING':
            self.state = 'BREAKDOWN'

        return False

    def charge_one_slot(self):
        """Charge the battery for one slot (called from Simulation)."""
        delta_soc = self.charging_power * 1e3
        self.soc_m = min(self.autonomy, self.soc_m + delta_soc)

    def needs_charging(self):
        # do not emit a request if already broken down.
        # `PARKED_SEARCHING` is allowed: the vehicle stopped for lack of a
        # station or an offer and must be able to re-emit its demand. It does
        # not consume in the meantime, so its SoC — hence `d_n` — stays valid.
        return (self.soc_m <= self.soc_threshold_m
                and self.state in ('DRIVING', 'PARKED_SEARCHING')
                and self.soc_m > self.config.SOC_BREAKDOWN_THRESHOLD)

    def draw_reservation_lead(self) -> int:
        """
        Planning horizon of the current request, in slots.

        The driver does not systematically book for the present moment: they
        target a slot `l_n` slots later. That delay is what makes an *early*
        cancellation possible — without it `t_arr = t_n` and every cancellation
        is mechanically late (see `utils.nominal_arrival` and
        `SimulationConfig.late_cancel_threshold`).

        Drawn on `rng_lead`, a **dedicated** stream. Sharing `rng_request` would
        shift the duration, radius and patience of every later request as soon
        as the horizon is enabled: the two arms of the ablation would then no
        longer differ by the horizon alone. A separate stream keeps the
        intervention clean, which is the whole point of `seeding.STREAM_CODES`.
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
    # Reputation
    # ------------------------------------------------------------------

    def record_score_event(self, index: int, signed_stake: float,
                           weight: float) -> float:
        """
        Record the outcome of a reservation and recompute the reputation score.

        Parameters
        ----------
        index : int
            Score slot to read and write (company, or 0 in global scope).
        signed_stake : float
            Normalised stake of the outcome, in [-1, 1]: positive for a
            presence, negative otherwise, relative to the largest stake of the
            company's scale (see `Station.update_car_score`).
        weight : float
            Weight of the event — reserved duration (`score_weighting =
            'duration'`) or 1 (`'event'`).

        The score is the weighted mean of the stakes in the window, **attenuated
        by how full that window is**:

            score = (Σ stake_i · weight_i / Σ weight_i) · (n / SCORE_MEMORY)

        The window always holds `SCORE_MEMORY` places; the places not yet filled
        count as "unknown", i.e. 0. The score therefore stays bounded in
        [-1, 1] — it is a mean of values in [-1, 1], scaled by a factor <= 1.

        Three properties follow, all intended:

        * *Right to be forgotten* — beyond `SCORE_MEMORY` reservations, the
          oldest ones leave the window.
        * *Effective redemption* — without the attenuation, a **single**
          negative outcome was enough to reach the floor (mean of a single
          event). The vehicle became ineligible everywhere, therefore received
          no further reservation, and its window could no longer turn: the right
          to be forgotten was inoperative, measured at 0 redemptions out of 9
          sanctioned vehicles. Reaching the floor now requires a *sustained*
          degradation, and a badly rated vehicle keeps being served by the least
          risk-averse stations — hence keeps a way back up.
        * *Reliability, not seniority* — it is a rate, not a cumulative sum. A
          vehicle that has driven a lot is no longer mechanically better rated
          than a reliable but less active one. And a vehicle with no history
          (score 0, "unknown") is no longer confused with a vehicle whose record
          is exactly balanced.

        The weight now acts only *relatively*, inside the window: a long
        reservation weighs more than a short one in the mean, but a window of
        events of equal duration yields the same score whatever that duration
        is. That is the counterpart of the bounding.
        """
        hist = self.score_history[index]
        hist.append((float(signed_stake), max(0., float(weight))))

        total_w = sum(w for _, w in hist)
        if total_w > 0.:
            mean = sum(stake * w for stake, w in hist) / total_w
        else:
            # All weights zero: fall back on the plain mean rather than losing
            # the information.
            mean = sum(stake for stake, _ in hist) / len(hist)

        confidence = len(hist) / float(hist.maxlen)
        self.score[index] = float(np.clip(mean * confidence, -1., 1.))
        return self.score[index]

    def reset_score(self):
        """Reset score and history (vehicle with no known past)."""
        self.score[:] = 0.
        for hist in self.score_history:
            hist.clear()

    def widen_search(self) -> bool:
        """
        Widen the search radius to re-emit the current demand.

        Returns True if a retry is still possible, False if the
        `MAX_SEARCH_RETRIES` budget is exhausted — in which case the caller must
        make the vehicle give up rather than leave it parked indefinitely.

        The widened radius deliberately exceeds `MAX_RAY_SEARCH`, which bounds
        the routine search: here the vehicle is stuck and looks further than
        usual. It stays bounded by the grid diagonal.

        Neither `d_n`, nor `g_n`, nor `l_n` is re-drawn: this is the *same*
        demand being re-emitted, and re-drawing those values would consume
        randomness at a rate depending on the method under test — the vehicle
        streams would diverge between BRAM-EV and Greedy.
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
        Re-emit the current demand from the current position.

        The demand identifier is kept: from the user's point of view this is a
        single charging need, whose end-to-end latency is being measured. Only
        the emission date moves forward, so that the nominal slot
        (`t_n + l_n + travel`) and the early-cancellation trigger
        (`t_c > reservation_slot`) stay consistent with the current time.

        The vehicle has been stopped since the previous attempt, so its position
        and SoC have not changed: `d_n` remains valid.
        """
        if self.request is None:
            raise RuntimeError("reemit_request without a pending request")
        self.request['t_n'] = current_time
        self.request['loc'] = (self.x, self.y)
        self.nb_request += 1
        return self.request

    def give_up_search(self):
        """Give up once the retry budget is exhausted: the vehicle drives on."""
        self.request = None
        self.search_retries = 0
        self.set_state('DRIVING')

    def update_schedule_requested(self, min_dist):
        """FIX: == → = (assignment)"""
        t_arr = utils.nominal_arrival(self.request['t_n'],
                                      self.request.get('l_n', 0),
                                      min_dist, self.config)
        t_dep = int(t_arr + self.request['d_n'])
        t_arr = min(t_arr, self.config.TOTAL_TIME - 1)
        t_dep = min(t_dep, self.config.TOTAL_TIME)
        self.schedule_requested[t_arr:t_dep] = 1

    def compute_utility(self, offer, request, min_dist):
        """
        FIX: distance-normalisation parenthesis corrected.
        Signature aligned with choose_offer (min_dist as a parameter).
        """
        d_n = request['d_n']
        if d_n <= 1:
            return 1.0   # maxEnergyDif = 0 would be impossible
        r_n = request['r_n']
        g_n = request['g_n']
        # The planning horizon `l_n` must enter here: without it, the delay the
        # driver actually wanted would be counted as endured waiting,
        # `waitingTime / maxWaitingTime` would exceed 1 and the final
        # `max(0., u)` would flatten *every* utility to zero — the offer ranking
        # would become arbitrary, with no error and no warning.
        t_hat_arr = utils.nominal_arrival(request['t_n'], request.get('l_n', 0),
                                          offer.distance, self.config)

        energyDif    = d_n - offer.d_prop
        maxEnergyDif = d_n - 1

        distance    = offer.distance
        maxDistance = r_n
        minDistance = min_dist

        waitingTime    = max(0, offer.t_arr - t_hat_arr)
        maxWaitingTime = g_n if g_n > 0 else 1

        # Distance normalisation: (d - dmin) / (dmax - dmin)
        dist_range = maxDistance - minDistance
        norm_dist = (distance - minDistance) / dist_range if dist_range > 0 else 0.

        u = (1.
             - self.pref['energy'] * (energyDif / maxEnergyDif)
             - self.pref['dist']   * norm_dist
             - self.pref['wait']   * (waitingTime / maxWaitingTime))
        return max(0., u)

    def rank_offers(self, offers, request, min_dist, criterion='utility'):
        """
        Rank the offers, best one first.

        The vehicle tries to confirm in that order: if the station refuses the
        confirmation (offer expired, or slot no longer free), it falls back on
        the next offer instead of giving up.

        Parameters
        ----------
        criterion : {'utility', 'nearest', 'waiting', 'load', 'random'}
            `'utility'` — decreasing multi-criteria utility (default, BRAM-EV).
            `'nearest'` — increasing distance: the `bramev_nearest_offer`
            variant of the ablation study, which measures what the
            energy/distance/waiting trade-off actually buys.
            `'waiting'` — increasing waiting time (`min_waiting` baseline).
            `'load'` — increasing future occupancy rate (`load_aware` baseline).
            `'random'` — uniform draw among the offers received
            (`random_feasible` baseline). Every offer received is feasible by
            construction: the station built it from its own calendar and
            revalidates it at confirmation.

        The utility is computed in every case: it remains the reported
        satisfaction measure (`car.u_total`), even when it does not drive the
        choice.

        Tie-breaks are explicit and deterministic (utility, then station id): two
        executions of the same world rank identically. The `'random'` criterion
        draws on `rng_choice`, a dedicated stream, so it does not shift the other
        draws of the vehicle.
        """
        if criterion not in OFFER_CRITERIA:
            raise ValueError(
                f"Unknown selection criterion: {criterion!r}. "
                f"Expected one of {list(OFFER_CRITERIA)}."
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
            # Canonical order first: the permutation must not depend on the
            # order in which the offers arrived, which follows station order.
            scored.sort(key=lambda pair: pair[0].station_id)
            order = self.rng_choice.permutation(len(scored))
            scored = [scored[i] for i in order]
        else:
            scored.sort(key=lambda pair: pair[1], reverse=True)
        return scored

    def _waiting_slots(self, offer, request) -> int:
        """Endured waiting: gap between the proposed slot and the targeted one."""
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
