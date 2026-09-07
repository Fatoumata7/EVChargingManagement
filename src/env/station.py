"""
station.py — Charging station agent
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
            Explicit parameters (loc, nb_charg_spot, alpha) coming from a
            `WorldSpec`. When provided, no random draw happens here: the station
            is rebuilt identically for every method being compared. When None,
            historical behaviour (random draw).
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
            self.alpha = random.uniform(0.1, 0.9)  # profit vs. risk weight

        self.strategy = None   # injected by Society.add_station()
        self.alpha_save = [self.alpha]

        # --- method flags (see src/experiments/methods.py)
        # Defaults = BRAM-EV. `Simulation` overrides them at initialisation,
        # once the method is known: the drawn world stays identical from one
        # method to the next, only the way it is read changes.
        self.score_index = society_id    # index read in `car.score`
        self.score_weighting = 'duration'  # 'duration' | 'event'

        self.T = config.TOTAL_TIME
        self.schedule = np.full((self.nb_charg_spot, self.T), -1, dtype=int)

        # Calendar version per charger: incremented on every write.
        # An offer carries the version seen at issuing time; a mismatch signals
        # that the calendar moved between the offer and the confirmation.
        self.charger_version = np.zeros(self.nb_charg_spot, dtype=int)
        self._offer_counter = 0

        # --- count metrics
        self.nb_pres = 0
        self.nb_no_show = 0
        self.nb_early_canc = 0
        self.nb_late_canc = 0
        self.nb_reservations = 0

        self.nb_station_level_rejections = 0
        self.nb_request = 0

        # --- cumulative occupancy
        # `schedule` holds a *current* state: every session end or cancellation
        # resets its slots to -1. Reading it at the end of a run therefore
        # yielded a zero occupancy rate for every method. These two counters are
        # cumulative and survive releases.
        self.nb_slots_reserved = 0   # charger-slots written to the calendar
        self.nb_slots_served = 0     # charger-slots actually spent charging

        # --- reservations closed by an exogenous event
        self.nb_breakdown_canc = 0   # vehicle broke down before its session
        self.nb_unresolved = 0       # reservation still open at the end of the horizon

        # --- offer safety
        self.nb_offer_issued = 0     # offers issued
        self.nb_offer_expired = 0    # offers not retained by the vehicle / TTL exceeded
        self.nb_confirm_refused = 0  # confirmations refused at revalidation
        self.nb_stale_confirm = 0    # confirmations accepted despite a stale version

    # ------------------------------------------------------------------
    # Method
    # ------------------------------------------------------------------

    def apply_method(self, spec, config=None):
        """
        Apply the flags of a `MethodSpec` to this station.

        Three internal mechanisms are concerned:

        * `reputation_scope` — `'society'`: each company keeps its own score
          (the score is an asset local to an operator); `'global'`: every
          station reads and writes slot 0, and reputation becomes a shared
          public good.
        * `score_weighting` — `'duration'`: the penalty is proportional to the
          reserved duration; `'event'`: flat penalty per event.
        * `alpha_mode` — `'fixed'`: the profit/risk trade-off is the same for
          every station (`config.ALPHA_FIXED`), which neutralises the initial
          heterogeneity of the alphas.

        Called by `Simulation.__init__`: the `WorldSpec` stays the source of
        truth for the world, the method only changes how it is read.
        """
        self.score_index = 0 if spec.reputation_scope == 'global' else self.society_id
        self.score_weighting = spec.score_weighting

        if spec.alpha_mode == 'fixed':
            alpha = float(getattr(config or self.config, 'ALPHA_FIXED', 0.5))
            self.alpha = alpha
            # `alpha_save[0]` documents the alpha actually used: otherwise the
            # alpha table would stay the one of the world, not of the method.
            self.alpha_save = [alpha]

    # ------------------------------------------------------------------
    # Score
    # ------------------------------------------------------------------

    def update_car_score(self, car_agent, status, d_n):
        """
        Record the outcome of a reservation in the vehicle's reputation.

        The stake of the outcome is read from the company's scale
        (`self.strategy`) then **normalised by the largest stake of that
        scale**, which brings it into [-1, 1]: positive for a presence, negative
        otherwise. The vehicle averages those over its `SCORE_MEMORY` last
        reservations (see `Car.record_score_event`).

        Normalising by `max(mu)` rather than by a constant preserves the order
        and the ratios of the scale — a company that punishes a no-show twice as
        hard as a late cancellation keeps doing so — while putting the scores of
        two companies on the same axis.

        The weight of the event stays the reserved duration (`score_weighting =
        'duration'`, default) or 1 (`'event'`: flat penalty); it weighs the mean
        instead of multiplying an unbounded cumulative sum.
        """
        mu = self.strategy
        normalizer = max(mu.values())
        if normalizer <= 0:
            return 0.

        stake = mu[status] if status in mu else mu['abs']
        signed = (+stake if status == 'pres' else -stake) / normalizer
        weight = float(d_n) if self.score_weighting == 'duration' else 1.0
        return car_agent.record_score_event(self.score_index, signed, weight)

    # ------------------------------------------------------------------
    # ILP optimisation
    # ------------------------------------------------------------------

    def process_demands(self, station_demands, t_c):
        """
        Solve the allocation problem and return a list of (Car, Offer).

        Contiguity
        ----------
        The model requires the slots allocated to a demand to form **a single
        contiguous block on a single charger**. This is obtained with a rising
        edge variable `s[n,j,t]` ("the charge of n starts at t on j") allowing at
        most one rising edge per demand:

            s[n,j,t] >= a[n,j,t] - a[n,j,t-1]      (missing a => 0)
            sum_{j,t} s[n,j,t] <= 1

        The duration stays variable (partial offer allowed, <= d_n), but
        `[t_arr, t_dep)` now covers exactly `d_prop` slots: an offer can no
        longer be an interval rebuilt from disjoint slots.
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

            # Nominal slot = emission + planning horizon + travel.
            # `t_max_n`, the window of `a[n,j,t]` and the penalty `D` of the
            # objective are all defined relative to `t_hat_arr`: they follow the
            # shift with no further change.
            arr = utils.nominal_arrival(req['t_n'], req.get('l_n', 0),
                                        dist, self.config)
            t_hat_arr[n] = arr
            t_hat_dep[n] = arr + req['d_n']
            d_n[n] = req['d_n']
            g_n[n] = req['g_n']
            scores[n] = float(car.score[self.score_index])

        # Decision variables: a[n,j,t] = 1 if n occupies charger j at slot t
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

        # Constraint: a single charger per demand
        for n in n_list:
            solver.Add(solver.Sum(y[n, j] for j in range(self.nb_charg_spot)) <= 1)

        for (n, j, t), var in a.items():
            solver.Add(var <= y[n, j])

        # Capacity constraint
        for j in range(self.nb_charg_spot):
            for t in range(t_c, T):
                solver.Add(
                    solver.Sum(a[n, j, t] for n in n_list if (n, j, t) in a) <= 1
                )

        # Duration constraint (<= d_n, not =, so partial offers stay allowed)
        for n in n_list:
            solver.Add(
                solver.Sum(
                    a[n, j, t]
                    for j in range(self.nb_charg_spot)
                    for t in range(T)
                    if (n, j, t) in a
                ) <= d_n[n]
            )

        # Contiguity constraint: at most one rising edge per demand.
        # A slot missing from `a` (charger already busy, or out of the window)
        # counts as 0, so resuming after a gap would count a second rising edge.
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

        # Aggregated objective
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
                self.nb_station_level_rejections += 1
                continue

            times = sorted(t for (nn, j, t), var in a.items()
                           if nn == n and j == j_selected and var.solution_value() > 0.5)
            if not times:
                # demand that could not be satisfied
                self.nb_station_level_rejections += 1
                continue

            t_arr, t_dep = times[0], times[-1] + 1
            # Guaranteed by the contiguity constraint
            assert t_dep - t_arr == len(times), (
                f"Station {self.m}: non-contiguous slots for demand {n} "
                f"({times})"
            )
            assert np.all(self.schedule[j_selected, t_arr:t_dep] == -1), (
                f"Station {self.m}: slots already booked offered to {n}"
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
        """Issue a timestamped, versioned offer with a limited validity."""
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
            charger_version=int(self.charger_version[charger_id]),
            station_load=self.future_occupancy_rate(t_c)
        )

    # ------------------------------------------------------------------
    # Reservation & schedule
    # ------------------------------------------------------------------

    def validate_offer(self, offer, t_c=None):
        """
        Revalidate an offer at confirmation time.

        Returns
        -------
        (ok, reason) : (bool, str | None)

        The authoritative check is the actual state of the calendar: an offer
        whose charger version changed stays confirmable as long as its slots are
        still free (the normal case: another charger, or another interval of the
        same charger, was booked in the meantime). The version mismatch is then
        counted (`nb_stale_confirm`) rather than refused.
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
        Confirm an offer after revalidation.

        Returns
        -------
        bool
            True if the reservation was written to the calendar. False if the
            offer was refused (it then moves to status REJECTED and can no
            longer be confirmed).
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
        """Count one charger-slot actually spent charging.

        Called by the simulation loop at every slot of active charging. The gap
        with `nb_slots_reserved` is exactly what no-shows and late cancellations
        cost the station: slots blocked and then never used.
        """
        self.nb_slots_served += 1

    def expire_offer(self, offer):
        """Expire an offer that was not retained (never confirmable again)."""
        if offer.is_pending():
            offer.expire()
            self.nb_offer_expired += 1

    def release_reservation(self, car_id, offer):
        """Release the reserved slots (on cancellation or session end)."""
        j = offer.charger_id
        mask = self.schedule[j, :] == car_id
        if np.any(mask):
            self.schedule[j, mask] = -1
            self.charger_version[j] += 1

    def get_current_charger_and_slot(self, car_id, t_c):
        """Return (j, True) if the vehicle should be charging at t_c."""
        for j in range(self.nb_charg_spot):
            if 0 <= t_c < self.T and self.schedule[j, t_c] == car_id:
                return j, True
        return None, False

    def is_session_finished(self, car_id, t_c):
        """Return True if the vehicle has no slot left from t_c onwards."""
        for j in range(self.nb_charg_spot):
            if np.any(self.schedule[j, t_c:] == car_id):
                return False
        return True

    def future_occupancy_rate(self, t_c: int) -> float:
        """
        Share of charger-slots already booked between `t_c` and the end of the
        horizon.

        Measures the *upcoming* load of the station, the only one that matters
        to a vehicle looking for a plug: `occupancy_rate` (output report) spans
        the whole horizon, past included.

        Since the calendar is only written at confirmation
        (`confirm_reservation`), pending offers are not counted: two vehicles
        served in the same batch therefore see the same load.
        """
        t = max(0, min(int(t_c), self.T))
        remaining = self.schedule[:, t:]
        if remaining.size == 0:
            return 1.
        return float(np.count_nonzero(remaining != -1) / remaining.size)

    def total_nb_allocated_slot(self):
        return int(np.sum(self.schedule != -1))

    def slot_capacity(self) -> int:
        """Total number of charger-slots offered over the horizon."""
        return int(self.nb_charg_spot * self.T)

    def outcomes_report(self) -> dict:
        """Outcomes of the confirmed reservations + offer-protocol health."""
        capacity = max(1, self.slot_capacity())
        return {
            'station_id':                  self.m,
            'society_id':                  self.society_id,
            'nb_charg_spot':               self.nb_charg_spot,
            'alpha':                       round(float(self.alpha), 4),
            'score_index':                 self.score_index,
            'score_weighting':             self.score_weighting,
            'nb_request':                  self.nb_request,
            'nb_station_level_rejections': self.nb_station_level_rejections,
            'nb_offer_issued':             self.nb_offer_issued,
            'nb_offer_expired':            self.nb_offer_expired,
            'nb_confirm_refused':          self.nb_confirm_refused,
            'nb_stale_confirm':            self.nb_stale_confirm,
            'nb_reservations':             self.nb_reservations,
            'nb_pres':                     self.nb_pres,
            'nb_no_show':                  self.nb_no_show,
            'nb_early_canc':               self.nb_early_canc,
            'nb_late_canc':                self.nb_late_canc,
            'nb_breakdown_canc':           self.nb_breakdown_canc,
            'nb_unresolved':               self.nb_unresolved,
            'nb_slots_reserved':           self.nb_slots_reserved,
            'nb_slots_served':             self.nb_slots_served,
            # Share of the horizon capacity booked / actually used.
            # Their gap quantifies the slots blocked and then wasted.
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
