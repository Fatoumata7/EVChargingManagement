"""
simulation_greedy.py
Version GREEDY :
- le véhicule contacte UNIQUEMENT la station la plus proche
- il accepte systématiquement l'offre reçue
- pas de comparaison d'offres / utility maximization
"""

import math
import time
import numpy as np
from loguru import logger

import src.experiments.config as cfg

from src.env.visualizer import Visualizer
from src.metrics.metrics import MetricsCollector, BreakdownTracker


class SimulationGreedy:

    def __init__(self, cars, stations, societies, t_max,
                 config: cfg.SimulationConfig):

        self.t_max = t_max
        self.current_t = 0

        self.cars = cars
        self.stations = stations
        self.societies = societies

        self.config = config

        self.nb_demands = 0

        self.viz = Visualizer(config)

        self._driving_to_station = {}

        self.metrics = MetricsCollector(
            cars,
            stations,
            config
        )

        self.breakdowns = BreakdownTracker()
        self._broken_cars = set()

    # ==========================================================
    # RUN
    # ==========================================================

    def run(self, file, print_metrics=True):

        for t in range(self.t_max):

            self.current_t = t

            self.step(
                t,
                self.config.log_iter,
                file=file
            )

        print(
            f"\n\n=== GREEDY Simulation terminée ({self.t_max} slots) ===",
            file=file
        )

        if print_metrics:
            self.metrics.print_report()
            self.breakdowns.print_report()

    # ==========================================================
    # STEP
    # ==========================================================

    def step(self, t_c: int, log_iter: int, file):

        # ------------------------------------------------------
        # LOG
        # ------------------------------------------------------

        str_log_tmp = (
            f'\n--------------------------------------------- '
            f'INSTANT {t_c}/{self.config.TOTAL_TIME} '
            f'---------------------------------------------\n'
        )

        file.write(str_log_tmp)

        if (((t_c + 1) % log_iter) == 0) or ((t_c + 1) == self.config.TOTAL_TIME): 
            logger.info(f'INSTANT {t_c + 1}/{self.config.TOTAL_TIME}')

        # ------------------------------------------------------
        # 0. Déplacement vers station
        # ------------------------------------------------------

        arrived = []

        for car_idx, target_station in list(self._driving_to_station.items()):

            car = self._get_car(car_idx)

            dist = self._get_distance(car, target_station)

            print(
                f'\ncar_{car.idx} '
                f'{car.state} '
                f'-> station_{target_station.m} '
                f'REMAINING DISTANCE {dist * 1e-3:.2f}km',
                file=file
            )

            if car.update_state(target_station.loc):

                arrived.append(car_idx)

                print(
                    f'\ncar_{car.idx} ARRIVED station_{target_station.m}',
                    file=file
                )

        for car_idx in arrived:
            del self._driving_to_station[car_idx]

        # ------------------------------------------------------
        # 1.a Déplacement libre
        # ------------------------------------------------------

        for car in self.cars:

            if car.state == 'DRIVING':
                car.update_state()

        # ------------------------------------------------------
        # 1.b Pannes
        # ------------------------------------------------------

        self._step_breakdown_detection(
            t_c,
            file=file
        )

        # ------------------------------------------------------
        # 2. DEMANDES GREEDY
        # ------------------------------------------------------

        id_demand = t_c * len(self.cars)

        for car in self.cars:

            if not car.needs_charging():
                continue

            print(
                f'\ncar_{car.idx} NEED CHARGING',
                file=file
            )

            req = car.emit_request(
                t_c,
                (car.x, car.y),
                id_demand
            )

            self.metrics.record_demand_emitted(id_demand)

            self.nb_demands += 1

            car.set_state('REQUESTING')

            # --------------------------------------------------
            # GREEDY :
            # station la plus proche uniquement
            # --------------------------------------------------

            nearest_station, min_dist = self._get_nearest_station(
                req['loc'][0],
                req['loc'][1]
            )

            if nearest_station is None:

                car.set_state('DRIVING')
                continue

            print(
                f'\n-> GREEDY nearest station = '
                f'{nearest_station.m} '
                f'({min_dist * 1e-3:.2f} km)',
                file=file
            )

            car.update_schedule_requested(min_dist)

            # --------------------------------------------------
            # Process unique station
            # --------------------------------------------------

            timing_rec = self.metrics.record_station_processing_start(
                nearest_station.m,
                id_demand
            )

            offers = nearest_station.process_demands(
                [(car, req)],
                t_c
            )

            timing_rec.t_end = time.perf_counter()

            self.metrics.record_demand_responded(
                car.request['n'],
                nearest_station.m
            )

            # --------------------------------------------------
            # Aucune offre
            # --------------------------------------------------

            if not offers:

                car.set_state('DRIVING')
                continue

            # --------------------------------------------------
            # GREEDY :
            # accepte automatiquement la première offre
            # --------------------------------------------------

            _, offer = offers[0]

            print(
                f'\n----- GREEDY ACCEPTED OFFER:',
                file=file
            )

            offer.display_offer(file=file)

            nearest_station.confirm_reservation(
                car.idx,
                offer
            )

            # --------------------------------------------------
            # Pas de comportement stochastique
            # --------------------------------------------------

            car.set_behavior('pres')

            # --------------------------------------------------
            # Metrics
            # --------------------------------------------------

            t_hat_arr = math.ceil(
                car.request['t_n']
                + offer.distance / self.config.CAR_SPEED
            )

            waiting_slots = max(
                0,
                offer.t_arr - t_hat_arr
            )

            self.metrics.record_offer_accepted(
                car,
                offer,
                waiting_slots
            )

            # --------------------------------------------------
            # Départ vers station
            # --------------------------------------------------

            car.set_reservation(offer)

            car.nb_sessions += 1

            car.update_car_speed()

            car.set_state('DRIVING_TO_STATION')

            self._driving_to_station[car.idx] = nearest_station

        # ------------------------------------------------------
        # 5. Recharge active
        # ------------------------------------------------------

        for car in self.cars:

            if (
                car.state not in (
                    'AT_STATION',
                    'CHARGING',
                    'WAITING'
                )
                or car.reservation is None
            ):
                continue

            target_station = self._get_station(
                car.reservation.station_id
            )

            _, charging_now = (
                target_station.get_current_charger_and_slot(
                    car.idx,
                    t_c
                )
            )

            if charging_now:

                car.set_state('CHARGING')

                car.charge_one_slot()

            elif car.state == 'AT_STATION':

                car.set_state('WAITING')

            if (
                target_station.is_session_finished(
                    car.idx,
                    t_c + 1
                )
                or car.soc_m >= 0.99 * car.autonomy
            ):

                target_station.update_car_score(
                    car,
                    'pres',
                    car.reservation.d_prop
                )

                car.set_state('DRIVING')

                car.reservation = None
                car.request = None

        # ------------------------------------------------------
        # VISUALISATION
        # ------------------------------------------------------

        if self.config.VISUALIZE:

            time.sleep(self.config.VIS_DELAY)

            self.viz.draw(
                self.cars,
                self.stations,
                t_c
            )

    # ==========================================================
    # UTILS
    # ==========================================================

    def _get_car(self, idx):

        return next(
            c for c in self.cars
            if c.idx == idx
        )

    def _get_station(self, sid):

        return next(
            s for s in self.stations
            if s.m == sid
        )

    def _get_distance(self, car, station):

        xc, yc = car.loc
        xs, ys = station.loc

        return np.sqrt(
            (xc - xs)**2 +
            (yc - ys)**2
        )

    # ----------------------------------------------------------
    # GREEDY helper
    # ----------------------------------------------------------

    def _get_nearest_station(self, x_n, y_n):

        nearest_station = None
        min_dist = float('inf')

        for s in self.stations:

            x_m, y_m = s.loc

            d = np.sqrt(
                (x_n - x_m)**2 +
                (y_n - y_m)**2
            )

            if d < min_dist:

                min_dist = d
                nearest_station = s

        return nearest_station, min_dist

    # ==========================================================
    # PANNE
    # ==========================================================

    def _step_breakdown_detection(self, t_c, file):

        for car in self.cars:

            # --------------------------------------------------
            # Nouvelle panne
            # --------------------------------------------------

            if (
                car.state == 'BREAKDOWN'
                and car.idx not in self._broken_cars
            ):

                self._broken_cars.add(car.idx)

                self.breakdowns.record(car, t_c)

                print(
                    f"\n  [PANNE] car_{car.idx}",
                    file=file
                )

                if car.reservation is not None:

                    s = self._get_station(
                        car.reservation.station_id
                    )

                    s.release_reservation(
                        car.idx,
                        car.reservation
                    )

                    self._driving_to_station.pop(
                        car.idx,
                        None
                    )

                    car.reservation = None
                    car.request = None

            # --------------------------------------------------
            # Reprise
            # --------------------------------------------------

            if (
                car.state == 'BREAKDOWN'
                and car.soc_m >
                self.config.SOC_BREAKDOWN_THRESHOLD * 5
            ):

                car.set_state('DRIVING')

                self._broken_cars.discard(car.idx)

                print(
                    f"\n  [REPRISE] car_{car.idx}",
                    file=file
                )