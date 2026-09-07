"""
simulation.py — Main loop with metrics collection

A single class covers **every** compared method; they differ only by switches
declared in `src/experiments/methods.py`:

    broadcast            the request goes to every eligible station, or to the
                         nearest one only (Nearest)
    use_reputation       stations update the behavioural score
    collective_learning  companies propagate the alpha of their best station
    offer_choice         the vehicle ranks the offers by multi-criteria utility
                         or by distance
    alpha_mode           alpha drawn per station, or identical everywhere
    reputation_scope     score per company, or a shared global score
    score_weighting      penalty proportional to the duration, or flat

The rest of the protocol (emission, ILP, confirmation, cancellations, metrics)
is shared: a fix therefore benefits every method, and the comparison cannot
diverge through copy-pasted code. That property is what makes the ablation study
interpretable — between two rungs of the ladder, *one single* switch changes.

Order within a slot
-------------------
1. cancellation decisions (start of slot, before any movement)
2. movements (towards a station, then free)
3. breakdown detection
4. request emission
5. ILP optimisation per station
6. selection then safe confirmation
7. active charging
8. collective learning
"""

import time
import numpy as np
from loguru import logger

import src.env.utils as utils
import src.experiments.config as cfg
import src.experiments.methods as methods
from src.metrics.metrics import MetricsCollector, BreakdownTracker, BehaviorTracker


class Simulation:

    #: Component flags, per method. A view derived from the registry, kept for
    #: the code (and the tests) that queried `Simulation.MODES`.
    MODES = {
        name: {'broadcast': spec.broadcast,
               'use_reputation': spec.use_reputation,
               'collective_learning': spec.collective_learning}
        for name, spec in methods.METHODS.items()
    }

    def __init__(self, cars, stations, societies, t_max, config: cfg.SimulationConfig,
                 mode: str = 'bramev'):
        """
        Parameters
        ----------
        mode : str
            Name of a method of the `src/experiments/methods.py` registry
            (aliases accepted). The world received is *identical* whatever the
            method: the flags only change the way it is exploited, which is the
            condition for attributing a measured gap to a component rather than
            to a draw.
        """
        try:
            spec = methods.resolve(mode)
        except KeyError as exc:
            raise ValueError(str(exc)) from exc

        self.method    = spec
        self.mode      = spec.name
        self.broadcast           = spec.broadcast
        self.use_reputation      = spec.use_reputation
        self.collective_learning = spec.collective_learning
        self.offer_choice        = spec.offer_choice

        self.t_max     = t_max
        self.current_t = 0
        self.cars      = cars
        self.stations  = stations
        self.societies = societies
        self.config    = config
        self.nb_demands = 0

        # The internal mechanisms carried by the stations (score scope, score
        # weighting, fixed alpha) are applied here, after the world has been
        # drawn: `WorldSpec` remains the source of truth for the environment.
        for station in stations:
            station.apply_method(spec, config)

        # O(1) index: `next(...)` over the whole list at every access was the
        # hot spot of the loop for 250 vehicles × 40 stations.
        self._car_by_idx     = {c.idx: c for c in cars}
        self._station_by_id  = {s.m: s for s in stations}

        # The pygame window is only opened when visualization is requested:
        # essential to run the experiment grid headless.
        self.viz = None
        if getattr(config, 'VISUALIZE', False):
            from src.env.visualizer import Visualizer
            self.viz = Visualizer(config)

        self._driving_to_station = {}
        self.metrics = MetricsCollector(cars, stations, config)

        self.breakdowns = BreakdownTracker()
        self.behaviors  = BehaviorTracker(config)
        self._broken_cars = set()   # car.idx of the cars currently broken down

    # ------------------------------------------------------------------
    def run(self, file, print_metrics=True):
        for t in range(self.t_max):
            self.current_t = t
            self.step(t, self.config.log_iter, file=file)
        self._finalize(file)
        print(f"\n\n=== Simulation finished ({self.t_max} slots) ===", file=file)
        if print_metrics:
            self.metrics.print_report()
            self.breakdowns.print_report()
            self.behaviors.print_report(self.config.BASE_CANCEL_PROB)
    # ------------------------------------------------------------------

    def step(self, t_c: int, log_iter: int, file):

        str_log_tmp = f'\n--------------------------------------------- INSTANT {t_c}/{self.config.TOTAL_TIME} ' + \
            '---------------------------------------------\n'
        file.write(str_log_tmp)
        if (((t_c + 1) % log_iter) == 0) or ((t_c + 1) == self.config.TOTAL_TIME):
            logger.info(f'INSTANT {t_c + 1}/{self.config.TOTAL_TIME}')

        # 1. Cancellations — decided at the start of the slot, before any move.
        #    (previously at the end of the slot: a vehicle due to cancel late
        #     had already reached the station and was counted as present)
        self._process_cancellations(t_c, file=file)

        # 2.a Movement towards a station
        arrived = []
        for car_idx, target_station in list(self._driving_to_station.items()):
            car = self._get_car(car_idx)
            dist = self._get_distance(car, target_station)
            print(f'\ncar_{car.idx} (soc: {car.soc_m:.2f} -> {(car.soc_m / car.autonomy) * 100:.2f}km) '
                  f'{car.state} station_{target_station.m} REMAINING DISTANCE {dist * 1e-3:.2f}km', file=file)
            if car.update_state(target_station.loc):
                arrived.append(car_idx)
                print(f'\ncar_{car.idx} ARRIVED station_{target_station.m}', file=file)
        for car_idx in arrived:
            del self._driving_to_station[car_idx]

        # 2.b Free movement
        for car in self.cars:
            if car.state == 'DRIVING':
                car.update_state()

        # 3. Breakdowns & handling
        self._step_breakdown_detection(t_c, file=file)

        # 4. Request emission
        demands   = {s.m: [] for s in self.stations}
        eligibles = {c.idx: None for c in self.cars}
        min_dists = {}

        for car in self.cars:

            # Vehicle already bound to a reservation
            if car.reservation is not None:
                continue

            if not car.needs_charging():
                continue

            # Unique demand identifier: (slot, vehicle). Previously
            # `t_c * len(cars)`, identical for every vehicle of a given slot —
            # the latency records overwrote each other. A retry keeps the
            # identifier: from the user's point of view this is a single
            # charging need, whose end-to-end latency is measured. Re-emitting
            # under a new identifier would inflate the number of demands and
            # sink the confirmation rate without any extra need having been
            # expressed.
            retrying = car.state == 'PARKED_SEARCHING'
            if retrying:
                req = car.reemit_request(t_c)
                id_demand = req['n']
            else:
                id_demand = self._demand_id(t_c, car.idx)
                req = car.emit_request(t_c, (car.x, car.y), id_demand)

            print(f'\ncar_{car.idx} NEED CHARGING (soc:{car.soc_m * 1e-3:.2f}km < {car.soc_threshold_m * 1e-3:.2f}km)'
                  + (f' [RETRY {car.search_retries}/{self.config.MAX_SEARCH_RETRIES}]'
                     if retrying else ''), file=file)
            print(f'\n-> REQUEST {req['n']}'
                  f' | DURATION: {req['d_n']} slots '
                  f'-> {req['d_n'] // self.config.NB_SLOTS_IN_ONE_HOUR}H '
                  f'{(req['d_n'] % self.config.NB_SLOTS_IN_ONE_HOUR) * self.config.SLOT_DURATION}min'
                  f' | RAY: {req['r_n']*1e-3:.2f}km'
                  f' | PATIENCE: {req['g_n']*5:.2f}min'
                  f' | LEAD: {req['l_n']} slots', file=file)
            car.set_state('REQUESTING')

            eligible, min_d, min_s = self._get_eligible_stations(
                req['loc'][0], req['loc'][1], req['r_n']
            )
            eligibles[car.idx] = eligible
            min_dists[car.idx] = min_d
            print(f'\n-> MIN_DIST = {min_d*1e-3:.2f}km, station {min_s.m if min_s else None}', file=file)
            print(f'\n-> {len(eligible)} ELIGIBLE STATION', file=file)

            # Stations actually contacted: every eligible one (BRAM-EV) or the
            # nearest one only (Greedy).
            targets = eligible if self.broadcast else ([min_s] if min_s else [])

            if retrying:
                self.metrics.record_demand_retry(
                    id_demand, nb_stations_contacted=len(targets))
            else:
                self.metrics.record_demand_emitted(
                    id_demand, car_id=car.idx, slot=t_c,
                    nb_stations_contacted=len(targets)
                )
                self.nb_demands += 1

            # No station within the radius: the vehicle stops and retries with a
            # widened radius rather than driving off at random.
            if not targets:
                self._retry_or_give_up(car, id_demand, 'no eligible station',
                                       t_c, file)
                continue

            car.update_schedule_requested(min_d)
            for s in targets:
                demands[s.m].append((car, req))

        # 5. ILP optimisation per station
        car_offers = {car.idx: [] for car in self.cars}

        for s in self.stations:
            if not demands[s.m]:
                continue

            batch_id = f"t{t_c}-s{s.m}"
            timing_rec = self.metrics.record_station_processing_start(
                s.m, batch_id, nb_demands=len(demands[s.m]))
            offers = s.process_demands(demands[s.m], t_c)
            timing_rec.t_end = time.perf_counter()

            for c, offer in offers:
                car_offers[c.idx].append(offer)
                self.metrics.record_demand_responded(c.request['n'], s.m)

        # 6. Offer selection then safe confirmation
        for car in self.cars:
            if car.state != 'REQUESTING':
                continue
            self._select_and_confirm(car, car_offers[car.idx],
                                     eligibles.get(car.idx) or [],
                                     min_dists.get(car.idx, 0.), t_c, file)

        # 7. Active charging
        for car in self.cars:

            if car.state not in ('AT_STATION', 'CHARGING', 'WAITING') or car.reservation is None:
                continue
            target_station = self._get_station(car.reservation.station_id)
            _, charging_now = target_station.get_current_charger_and_slot(car.idx, t_c)

            if charging_now:
                car.set_state('CHARGING')
                car.charge_one_slot()
                target_station.record_served_slot()

            elif car.state == 'AT_STATION':
                car.set_state('WAITING')

            if target_station.is_session_finished(car.idx, t_c + 1) or car.soc_m >= 0.99 * car.autonomy:
                target_station.nb_pres += 1
                if self.use_reputation:
                    target_station.update_car_score(car, 'pres', car.reservation.d_prop)
                self.behaviors.record_outcome(car.cancel_intent, 'pres')
                target_station.release_reservation(car.idx, car.reservation)
                car.set_state('DRIVING')
                car.clear_reservation()

        # 8. Company update
        if (self.collective_learning and t_c > 0
                and t_c % self.config.SOCIETY_UPDATE_INTERVAL == 0):
            logger.info('-> UPDATE SOCIETY STRATEGY')
            for society in self.societies:
                society.update_strategy(file=file)

        # --- VISUALIZATION
        if self.viz is not None:
            time.sleep(self.config.VIS_DELAY)
            self.viz.draw(self.cars, self.stations, t_c)

    # ------------------------------------------------------------------
    # Search retry
    # ------------------------------------------------------------------

    def _retry_or_give_up(self, car, demand_id, reason, t_c, file=None):
        """
        Search failure: the vehicle parks and retries with a widened radius, or
        gives up if its retry budget is exhausted.

        Stopping rather than driving on has two effects: the vehicle no longer
        consumes during an unsuccessful search — so it cannot break down for
        want of a charger — and it does not drift away from the stations it is
        trying to reach.
        """
        if car.widen_search():
            car.set_state('PARKED_SEARCHING')
            if file is not None:
                print(f'\ncar_{car.idx} PARKED_SEARCHING ({reason}) '
                      f'-> radius widened to {car.request["r_n"] * 1e-3:.2f}km '
                      f'[{car.search_retries}/{self.config.MAX_SEARCH_RETRIES}]',
                      file=file)
            return True

        self.metrics.record_demand_selection(demand_id)
        self.metrics.record_demand_confirmation(demand_id, False, 0)
        if file is not None:
            print(f'\ncar_{car.idx} SEARCH ABANDONED ({reason}) after '
                  f'{car.search_retries} retry(ies)', file=file)
        car.give_up_search()
        return False

    # ------------------------------------------------------------------
    # Selection & confirmation
    # ------------------------------------------------------------------

    def _select_and_confirm(self, car, offers, eligible, min_d, t_c, file):
        """
        The vehicle ranks the offers received (multi-criteria utility, or
        distance if `offer_choice == 'nearest'`) and confirms **only one**.

        Guarantees:
          * a single confirmed offer per demand;
          * every other one moves explicitly to EXPIRED — they can no longer be
            confirmed, even by mistake;
          * the station revalidates the offer (TTL, contiguity, slots actually
            free) before writing to the calendar; on refusal, the vehicle falls
            back on the next offer instead of giving up.
        """
        demand_id = car.request['n']
        car.nb_offers_received += len(offers)
        car.nb_rejected += max(0, len(eligible) - len(offers))

        if not offers:
            self._retry_or_give_up(car, demand_id, 'no offer received', t_c, file)
            return

        ranked = car.rank_offers(offers, car.request, min_d, self.offer_choice)
        self.metrics.record_demand_selection(demand_id)

        chosen, chosen_u, attempts = None, None, 0
        for offer, u in ranked:
            station = self._get_station(offer.station_id)
            attempts += 1
            if station.confirm_reservation(car.idx, offer, t_c):
                chosen, chosen_u = offer, u
                break
            car.nb_confirm_failed += 1
            print(f'\ncar_{car.idx} CONFIRM REFUSED {offer.offer_id} '
                  f'({offer.reject_reason})', file=file)

        # The offers not retained expire immediately.
        for offer, _ in ranked:
            if offer is not chosen:
                self._get_station(offer.station_id).expire_offer(offer)

        self.metrics.record_demand_confirmation(demand_id, chosen is not None, attempts)

        if chosen is None:
            self._retry_or_give_up(car, demand_id, 'no confirmation accepted',
                                   t_c, file)
            return

        print(f'\n----- CHOOSEN OFFER:', file=file)
        chosen.display_offer(file=file)

        target_station = self._get_station(chosen.station_id)

        behavior = car.draw_behavior()
        car.set_behavior(behavior)
        car.set_reservation(chosen)
        car.cancel_intent    = behavior
        car.reservation_slot = car.request['t_n']
        car.reservation_lead = max(0, chosen.t_arr - car.request['t_n'])
        self.behaviors.record_intent(behavior, car.reservation_lead)

        if behavior == 'abs':
            # The reservation stays active in the schedule: the slot is lost
            # until t_dep. The vehicle will never show up and stays put until
            # then (PARKED_NO_SHOW) — it gave up its trip, not only its charge.
            # Important consequence: a no-show no longer consumes for the whole
            # duration of its frozen slot, and can therefore no longer break
            # down because of it.
            car.set_state('PARKED_NO_SHOW')
            return

        # `t_hat_arr` includes the planning horizon: the delay wanted by the
        # driver is not endured waiting and must not degrade the quality-of-
        # service metric.
        t_hat_arr     = utils.nominal_arrival(car.request['t_n'],
                                              car.request.get('l_n', 0),
                                              chosen.distance, self.config)
        waiting_slots = max(0, chosen.t_arr - t_hat_arr)
        self.metrics.record_offer_accepted(car, chosen, waiting_slots)

        car.nb_sessions += 1
        car.u_total += chosen_u
        car.update_car_speed()
        car.set_state('DRIVING_TO_STATION')
        self._driving_to_station[car.idx] = target_station

    # ------------------------------------------------------------------
    # Cancellations
    # ------------------------------------------------------------------

    def _process_cancellations(self, t_c, file=None):
        """
        Realise the cancellation intents drawn at reservation time.

        Correction applied
        ------------------
        The former logic first reclassified the intent according to the time
        left, then required the recomputed class to match the intent. Since the
        request → arrival delay is almost always shorter than LATE_CANCEL_REF
        (12 slots = 1 h) while the trip lasts only a few slots, everything was
        classified as "late" and the "early" branch was **unreachable**: a
        vehicle with an `early` intent never cancelled and ended up counted as
        present.

        New logic: the intent determines *when* the cancellation happens, and
        the observed outcome is derived from the time actually left.

          early  → cancels as soon as the slot after the reservation (earliest)
          late   → cancels when <= threshold slots are left before the planned
                   arrival

        The threshold is `config.late_cancel_threshold(lead)`: bounded both by
        LATE_CANCEL_REF and by a fraction of the actual delay, so that both
        regimes are reachable. The observed outcome may therefore differ from
        the intent (an `early` intent on a very short-delay reservation is
        realised as `late`): `BehaviorTracker` records both.
        """

        # --------------------------------------------------
        # No-show (absence): slot occupied until t_dep
        # --------------------------------------------------
        for car in self.cars:

            if car.cancel_intent != 'abs' or car.reservation is None:
                continue

            if t_c < car.reservation.t_dep:
                continue

            s = self._get_station(car.reservation.station_id)
            s.release_reservation(car.idx, car.reservation)
            s.nb_no_show += 1
            if self.use_reputation:
                s.update_car_score(car, 'abs', car.reservation.d_prop)
            self.behaviors.record_outcome(car.cancel_intent, 'abs')

            self._driving_to_station.pop(car.idx, None)
            car.clear_reservation()
            if car.state not in ('BREAKDOWN',):
                car.set_state('DRIVING')

        # --------------------------------------------------
        # Early / late cancellation
        # --------------------------------------------------
        for car in self.cars:
            if car.reservation is None or car.cancel_intent not in ('early', 'late'):
                continue
            # A session already started can no longer be cancelled.
            if car.state == 'CHARGING':
                continue

            offer = car.reservation
            threshold  = self.config.late_cancel_threshold(car.reservation_lead or 0)
            slots_left = offer.t_arr - t_c

            if car.cancel_intent == 'early':
                trigger = t_c > car.reservation_slot
            else:
                trigger = slots_left <= threshold

            if not trigger:
                continue

            observed = 'early' if slots_left > threshold else 'late'

            s = self._get_station(offer.station_id)
            s.release_reservation(car.idx, offer)
            if observed == 'early':
                s.nb_early_canc += 1
            else:
                s.nb_late_canc += 1
            if self.use_reputation:
                s.update_car_score(car, observed, offer.d_prop)
            self.behaviors.record_outcome(car.cancel_intent, observed)

            if file is not None:
                print(f'\ncar_{car.idx} CANCEL {observed} (intent={car.cancel_intent}, '
                      f'slots_left={slots_left}, threshold={threshold}) station_{s.m}', file=file)

            self._driving_to_station.pop(car.idx, None)
            car.clear_reservation()
            car.set_state('DRIVING')

    # ------------------------------------------------------------------
    # Closing
    # ------------------------------------------------------------------

    def _finalize(self, file=None):
        """
        Resolve the reservations still open at the end of the horizon.

        Without this step, any reservation whose `t_dep` exceeds the horizon
        stayed counted as confirmed without ever receiving an outcome: the
        invariant `nb_reservations == sum of the outcomes` was false and the
        no-show rates under-estimated.
        """
        for car in self.cars:
            if car.reservation is None:
                continue
            s = self._get_station(car.reservation.station_id)
            if car.cancel_intent == 'abs':
                s.nb_no_show += 1
                self.behaviors.record_outcome('abs', 'abs')
            else:
                s.nb_unresolved += 1
                self.behaviors.record_outcome(car.cancel_intent, 'unresolved')
            s.release_reservation(car.idx, car.reservation)
            self._driving_to_station.pop(car.idx, None)
            car.clear_reservation()

        ok, errors = self.check_reservation_invariant()
        if not ok and file is not None:
            for err in errors:
                print(f'\n[INVARIANT] {err}', file=file)
        return ok

    def check_reservation_invariant(self):
        """
        Check, station by station, that every confirmed reservation received
        exactly one outcome.
        """
        errors = []
        for s in self.stations:
            outcomes = (s.nb_pres + s.nb_no_show + s.nb_early_canc
                        + s.nb_late_canc + s.nb_breakdown_canc + s.nb_unresolved)
            if outcomes != s.nb_reservations:
                errors.append(
                    f"Station {s.m}: {s.nb_reservations} reservations != "
                    f"{outcomes} outcomes (pres={s.nb_pres}, abs={s.nb_no_show}, "
                    f"early={s.nb_early_canc}, late={s.nb_late_canc}, "
                    f"breakdown={s.nb_breakdown_canc}, unresolved={s.nb_unresolved})"
                )
        return (not errors), errors

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------

    def results(self) -> dict:
        """Complete, serialisable result of one execution."""
        ok, errors = self.check_reservation_invariant()
        return {
            'mode':             self.mode,
            'method':           self.mode,
            'method_flags':     self.method.to_dict(),
            'seed':             self.config.SEED,
            'scenario':         self.config.SCENARIO_NAME,
            'config':           self.config.summary(),
            'nb_demands':       self.nb_demands,
            'metrics':          self.metrics.report(),
            'breakdowns':       {k: v for k, v in self.breakdowns.report().items()
                                 if k != 'records'},
            'behaviors':        self.behaviors.report(),
            'stations':         [s.outcomes_report() for s in self.stations],
            'invariant_ok':     ok,
            'invariant_errors': errors,
        }

    # ------------------------------------------------------------------
    def _demand_id(self, t_c, car_idx):
        """Unique identifier of a demand: a vehicle emits at most one request
        per slot (guarded by `car.reservation is None` + DRIVING state)."""
        return f"t{t_c:05d}-c{car_idx:05d}"

    def _get_car(self, idx):
        return self._car_by_idx[idx]

    def _get_station(self, sid):
        return self._station_by_id[sid]

    def _get_distance(self, car, station):
        xc, yc = car.x, car.y
        xs, ys = station.loc
        return np.sqrt((xc - xs)**2 + (yc - ys)**2)

    def _get_eligible_stations(self, x_n, y_n, r_n):
        """Return (eligible stations, minimal distance, nearest station)."""
        eligible, min_dist = [], float('inf')
        min_stat = None
        for s in self.stations:
            x_m, y_m = s.loc
            d = np.sqrt((x_n - x_m)**2 + (y_n - y_m)**2)
            if d <= r_n:
                eligible.append(s)
                if d < min_dist:
                    min_dist = d
                    min_stat = s
        return eligible, (min_dist if eligible else 0.), min_stat

    def _step_breakdown_detection(self, t_c, file):

        """Phase 3 — detect the new breakdowns and handle recovery."""

        for car in self.cars:

            # ── New breakdown ───────────────────────────────────────────
            if (car.state == 'BREAKDOWN'
                    and car.idx not in self._broken_cars):
                self._broken_cars.add(car.idx)
                self.breakdowns.record(car, t_c)
                print(f"\n  [BREAKDOWN] car_{car.idx} breaks down "
                    f"(soc={car.soc_m:.3f}) pos=({car.x:.0f},{car.y:.0f})", file=file)

                # Release the reservation if there was one
                if car.reservation is not None:
                    s = self._get_station(car.reservation.station_id)
                    s.release_reservation(car.idx, car.reservation)
                    s.nb_breakdown_canc += 1
                    if self.use_reputation:
                        s.update_car_score(car, 'abs', car.reservation.d_prop)
                    self.behaviors.record_outcome(car.cancel_intent, 'breakdown')
                    self._driving_to_station.pop(car.idx, None)
                    car.clear_reservation()

            # ── Recovery after a full charge ────────────────────────────
            # A car in BREAKDOWN can restart if its soc went back up
            # (case where it did reach a station despite soc~0)
            if (car.state == 'BREAKDOWN'
                    and car.soc_m > self.config.SOC_BREAKDOWN_THRESHOLD * 5):
                car.set_state('DRIVING')
                self._broken_cars.discard(car.idx)
                print(f"\n  [RECOVERY] car_{car.idx} restarts (soc={car.soc_m:.3f})", file=file)
