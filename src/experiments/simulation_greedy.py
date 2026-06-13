"""
simulation_greedy.py — Boucle principale avec collecte des métriques
"""

import math
import time
import numpy as np
from loguru import logger   

import src.experiments.config as cfg
from src.metrics.metrics import MetricsCollector
from src.env.visualizer import Visualizer
from src.metrics.metrics import MetricsCollector, BreakdownTracker


class SimulationGreedy:

    def __init__(self, cars, stations, societies, t_max, config: cfg.SimulationConfig):
        self.t_max     = t_max
        self.current_t = 0
        self.cars      = cars
        self.stations  = stations
        self.societies = societies
        self.config    = config
        self.nb_demands = 0

        self.viz = Visualizer(config)

        self._driving_to_station = {}
        self.metrics = MetricsCollector(cars, stations, config)

        self.breakdowns = BreakdownTracker()
        self._broken_cars = set()   # car.idx des voitures actuellement en panne

    # ------------------------------------------------------------------
    def run(self, file, print_metrics=True):
        for t in range(self.t_max):
            self.current_t = t
            self.step(t, self.config.log_iter, file=file)
        print(f"\n\n=== Simulation terminée ({self.t_max} slots) ===", file=file)
        if print_metrics:
            self.metrics.print_report()
            self.breakdowns.print_report()
            #print(f"\n  Pannes sèches : {self.breakdowns.count} cars", file=file)
    # ------------------------------------------------------------------
    
    def step(self, t_c: int, log_iter: int, file):

        str_log_tmp = f'\n--------------------------------------------- INSTANT {t_c}/{self.config.TOTAL_TIME} ' + \
            '---------------------------------------------\n'
        file.write(str_log_tmp)
        if (((t_c + 1) % log_iter) == 0) or ((t_c + 1) == self.config.TOTAL_TIME): 
            logger.info(f'INSTANT {t_c + 1}/{self.config.TOTAL_TIME}')
            
        # 0. Déplacement vers station
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

        # 1.a Déplacement libre
        for car in self.cars:
            if car.state == 'DRIVING':
                car.update_state()

        # 1.b Pannes & gestion
        self._step_breakdown_detection(t_c, file=file)

        # 2. Émission des requêtes
        demands   = {s.m: [] for s in self.stations}
        min_dists = {}
        id_demand = t_c * len(self.cars)

        for car in self.cars:

            # Véhicule déjà lié à une réservation
            if car.reservation is not None:
                continue

            if car.needs_charging():

                print(f'\ncar_{car.idx} NEED CHARGING (soc:{car.soc_m * 1e-3:.2f}km < {car.soc_threshold_m * 1e-3:.2f}km)', file=file)
                req = car.emit_request(t_c, (car.x, car.y), id_demand)
                print(f'\n-> REQUEST {req['n']}'
                      f' | DURATION: {req['d_n']} slots '
                      f'-> {req['d_n'] // self.config.NB_SLOTS_IN_ONE_HOUR}H '
                      f'{(req['d_n'] % self.config.NB_SLOTS_IN_ONE_HOUR) * self.config.SLOT_DURATION}min'
                      f' | RAY: {req['r_n']*1e-3:.2f}km'
                      f' | PATIENCE: {req['g_n']*5:.2f}min', file=file)
                self.metrics.record_demand_emitted(id_demand)
                self.nb_demands += 1
                car.set_state('REQUESTING')

                eligible, min_d, min_s = self._get_eligible_stations(
                    req['loc'][0], req['loc'][1], req['r_n']
                )
                print(f'\n-> MIN_DIST = {min_d*1e-3:.2f}km, station {min_s}', file=file)
                print(f'\n-> {len(eligible)} ELIGIBLE STATION', file=file)
                # --- fix: si rayon de recherche trop petit et pas d'eligible station, le véhicule continue de rouler
                if len(eligible) == 0:
                    car.set_state('DRIVING')
                min_dists[car.idx] = min_d

                if eligible:
                    car.update_schedule_requested(min_d)
                    #for s in eligible:
                    demands[min_s.m].append((car, req))
                else:
                    car.set_state('DRIVING')

        # 3. Optimisation ILP par station
        car_offers = {car.idx: [] for car in self.cars}

        for s in self.stations:
            if not demands[s.m]:
                continue

            timing_rec = self.metrics.record_station_processing_start(s.m, id_demand)
            offers = s.process_demands(demands[s.m], t_c)
            timing_rec.t_end = time.perf_counter()

            for c, offer in offers:
                car_offers[c.idx].append(offer)
                self.metrics.record_demand_responded(c.request['n'], s.m)

        # 4. Sélection de l'offre
        for car in self.cars:
            if car.state != 'REQUESTING':
                continue

            offers = car_offers[car.idx]
            min_d  = min_dists.get(car.idx, 0.)

            if not offers:
                car.set_state('DRIVING')
                continue

            best_offer, best_u = car.choose_offer(offers, car.request, min_d)
            if best_offer is not None:
                print(f'\n----- CHOOSEN OFFER:', file=file)
                best_offer.display_offer(file=file)
            if best_offer is None:
                car.set_state('DRIVING')
                continue

            target_station = self._get_station(best_offer.station_id)
            target_station.confirm_reservation(car.idx, best_offer)
            target_station.nb_reservations += 1

            behavior = np.random.choice(
                list(car.theta.keys()), p=list(car.theta.values())
            )
            car.set_behavior(behavior)

            if behavior == 'abs':
                # La réservation reste active dans le planning.
                # Le véhicule ne se présentera jamais.
                car.set_reservation(best_offer)
                car.set_state('DRIVING')
                continue

            t_hat_arr     = math.ceil(car.request['t_n'] + best_offer.distance / self.config.CAR_SPEED)
            waiting_slots = max(0, best_offer.t_arr - t_hat_arr)
            self.metrics.record_offer_accepted(car, best_offer, waiting_slots)

            car.set_reservation(best_offer)
            car.nb_sessions += 1
            car.u_total += best_u
            car.update_car_speed()
            car.set_state('DRIVING_TO_STATION')
            self._driving_to_station[car.idx] = target_station

        # 5. Recharge active
        for car in self.cars:

            if car.state not in ('AT_STATION', 'CHARGING', 'WAITING') or car.reservation is None:
                continue
            target_station = self._get_station(car.reservation.station_id)
            _, charging_now = target_station.get_current_charger_and_slot(car.idx, t_c)

            if charging_now:
                car.set_state('CHARGING')
                car.charge_one_slot()

            elif car.state == 'AT_STATION':
                car.set_state('WAITING')

            if target_station.is_session_finished(car.idx, t_c + 1) or car.soc_m >= 0.99 * car.autonomy:
                target_station.nb_pres += 1
                #target_station.update_car_score(car, 'pres', car.reservation.d_prop)
                car.set_state('DRIVING')
                car.reservation = None
                car.request = None

        # 6. Annulations
        self._process_cancellations(t_c)

        # 7. Mise à jour sociétés
        # if t_c > 0 and t_c % self.config.SOCIETY_UPDATE_INTERVAL == 0:
        #     logger.info('-> UPDATE SOCIETY STRATEGY', file=file)
        #     for society in self.societies:
        #         society.update_strategy(file=file)

        # --- VISUALISATION
        if self.config.VISUALIZE:
            time.sleep(self.config.VIS_DELAY)
            self.viz.draw(self.cars, self.stations, t_c)

    # ------------------------------------------------------------------
    def _process_cancellations(self, t_c):

        # --------------------------------------------------
        # No-show (absence)
        # --------------------------------------------------

        for car in self.cars:

            if car.behavior != 'abs' or car.reservation is None:
                continue

            # La réservation est totalement terminée
            if t_c == car.reservation.t_dep:

                s = self._get_station(car.reservation.station_id)

                s.release_reservation(
                    car.idx,
                    car.reservation
                )

                s.nb_no_show += 1
                #s.update_car_score(car, 'abs', car.reservation.d_prop)

                car.reservation = None
                car.request = None

        # --------------------------------------------------
        # Early/Late cancelation
        # --------------------------------------------------

        for car in self.cars:
            if car.state != 'DRIVING_TO_STATION' or car.reservation is None:
                continue
            if car.behavior not in ('early', 'late'):
                continue
            slots_left = car.reservation.t_arr - t_c
            status = 'late' if slots_left <= self.config.LATE_CANCEL_REF else 'early'
            should_cancel = (
                (status == 'early' and t_c == car.request['t_n'] + 1) or
                (status == 'late'  and slots_left == self.config.LATE_CANCEL_REF)
            )
            if not should_cancel:
                continue
            s = self._get_station(car.reservation.station_id)
            s.release_reservation(car.idx, car.reservation)
            if status == 'early':
                s.nb_early_canc += 1
            else:
                s.nb_late_canc += 1
            #s.update_car_score(car, status, car.reservation.d_prop)
            self._driving_to_station.pop(car.idx, None)
            car.set_state('DRIVING')
            car.reservation = None
            car.request = None

    # ------------------------------------------------------------------
    def _get_car(self, idx):
        return next(c for c in self.cars if c.idx == idx)

    def _get_station(self, sid):
        return next(s for s in self.stations if s.m == sid)
    
    def _get_distance(self, car, station):
        xc, yc = car.loc
        xs, ys = station.loc
        dist = np.sqrt((xc - xs)**2 + (yc - ys)**2)
        return dist

    def _get_eligible_stations(self, x_n, y_n, r_n):
        eligible, min_dist = [], float('inf')
        min_stat = -1
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

        """Phase 1b — détecte les nouvelles pannes et gère la reprise."""

        for car in self.cars:

            # ── Nouvelle panne ──────────────────────────────────────────
            if (car.state == 'BREAKDOWN'
                    and car.idx not in self._broken_cars):
                self._broken_cars.add(car.idx)
                self.breakdowns.record(car, t_c)
                print(f"\n  [PANNE] car_{car.idx} tombe en panne "
                    f"(soc={car.soc_m:.3f}) pos=({car.x:.0f},{car.y:.0f})", file=file)

                # Libère la réservation si elle existait
                if car.reservation is not None:
                    s = self._get_station(car.reservation.station_id)
                    s.release_reservation(car.idx, car.reservation)
                    #s.update_car_score(car, 'abs', car.request['d_n'])
                    self._driving_to_station.pop(car.idx, None)
                    car.reservation = None
                    car.request = None

            # ── Reprise après recharge complète ─────────────────────────
            # Une voiture en BREAKDOWN peut redémarrer si son soc a remonté
            # (cas où elle a quand même atteint une station malgré soc~0)
            if (car.state == 'BREAKDOWN'
                    and car.soc_m > self.config.SOC_BREAKDOWN_THRESHOLD * 5):
                car.set_state('DRIVING')
                self._broken_cars.discard(car.idx)
                print(f"\n  [REPRISE] car_{car.idx} redémarre (soc={car.soc_m:.3f})", file=file)

