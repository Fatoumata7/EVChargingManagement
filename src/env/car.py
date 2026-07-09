"""
car.py — Agent véhicule électrique
"""

import numpy as np
import math
import random

import src.env.utils as utils
import src.experiments.config as config


class Car:

    def __init__(self, idx: int, nb_society: int, config: config.SimulationConfig):

        self.config = config
        self.idx = idx
        self.loc = utils.init_pos(config)
        self.x, self.y = float(self.loc[0]), float(self.loc[1])
        self.soc_init = self.init_soc()
        self.autonomy = self.define_autonomy()
        self.soc_m = self.autonomy * self.soc_init # distance restante à parcourir avec état actuel de la batterie
        self.state = 'DRIVING'   # 'DRIVING', 'REQUESTING', 'DRIVING_TO_STATION', 'AT_STATION', 'CHARGING', 'WAITING', 'BREAKDOWN'
        self.request = None
        self.reservation = None
        self.behavior = None
        self.speed_to_station = None

        self.theta = self.generate_cancel_probabilities()
        self.pref = self.generate_preferences()
        self.charging_power = self.generate_charging_power()        # km/slot

        self.score = np.zeros(nb_society)
        self.u_total = 0.0
        self.nb_sessions = 0
        self.nb_rejected = 0
        self.nb_request = 0

        self.soc_threshold_m = utils.get_truncated_normal(
            mean=self.config.CAR_SOC_THRESHOLD_PARAMS['mean'],
            sd=self.config.CAR_SOC_THRESHOLD_PARAMS['sd'],
            low=self.config.CAR_SOC_THRESHOLD_PARAMS['low'],
            high=self.config.CAR_SOC_THRESHOLD_PARAMS['high']) * self.autonomy # seuil soc_m pour déclencher l'émission d'une requête

        self.schedule_requested = np.zeros(config.TOTAL_TIME)

    def init_soc(self):
        return random.uniform(self.config.CAR_INIT_SOC['low'],
                              self.config.CAR_INIT_SOC['high'])

    def set_state(self, new_state):
        valid = {'WAITING', 'DRIVING', 'CHARGING', 'REQUESTING',
                 'DRIVING_TO_STATION', 'AT_STATION', 'BREAKDOWN'}
        assert new_state in valid, f"État inconnu : {new_state}"
        self.state = new_state

    def set_reservation(self, best_offer):
        self.reservation = best_offer

    def set_behavior(self, behavior):
        self.behavior = behavior

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

    def generate_charging_duration_request(self, strategies):
        if self.soc_m >= self.autonomy * 0.95 :
            return 0
        weights   = [s[0] for s in strategies]
        intervals = [s[1] for s in strategies]
        idx_choice = np.random.choice(len(intervals), p=weights)
        low, high = intervals[idx_choice]
        target_soc = np.random.uniform(low, high) * self.autonomy   # en mètres
        if self.soc_m > target_soc:
            target_soc = self.autonomy
        needed_km = (target_soc - self.soc_m) * 1e-3                # en kilomètres
        return max(int(needed_km / self.charging_power) + 1, 1)

    def update_car_speed(self):
        if self.behavior == 'pres':
            reduce_factor = 1
        else:
            reduce_factor = random.choice(self.config.REDUCE_SPEED_FACTORS)
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
            move_axis = np.random.choice(['x', 'y'])
            #print(self.x, self.y)
            step = np.random.uniform(-1, 1) * self.config.CAR_SPEED
            if move_axis == 'x':
                self.x = np.clip(self.x + step, 0, self.config.C_GRID)
            else:
                self.y = np.clip(self.y + step, 0, self.config.C_GRID)
            #print(self.x, self.y)
        else:
            x_m, y_m = loc
            dx, dy = x_m - self.x, y_m - self.y
            if abs(dx) < threshold_at_station and abs(dy) < threshold_at_station:
                self.set_state('AT_STATION')
                return True
            move_axis = 'x' if abs(dx) >= abs(dy) else 'y'
            step_size = np.random.uniform(0, self.speed_to_station)
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
        # energy_per_unit = (self.config.ENERGY_CONSUMPTION['quantity_kW'] /
        #                 self.config.ENERGY_CONSUMPTION['distance_unit_m'])
        # self.soc = max(0., self.soc - dist * energy_per_unit)
        self.soc_m = max(0., self.soc_m - dist)

        # Vérifie panne après déplacement
        if self.soc_m <= self.config.SOC_BREAKDOWN_THRESHOLD and self.state == 'DRIVING':
            self.state = 'BREAKDOWN'

        return False

    def charge_one_slot(self):
        """Recharge la batterie d'un slot (appelé depuis Simulation)."""
        # km_per_slot = self.charging_power
        # delta_soc = km_per_slot / self.autonomy
        delta_soc = self.charging_power * 1e3
        #print(f'delta_soc = {delta_soc * 1e-3:.2f}km')
        self.soc_m = min(self.autonomy, self.soc_m + delta_soc)
        #print(f'self.soc_m = {self.soc_m * 1e-3:.2f}km')
    
    def needs_charging(self):
        # ne pas émettre de requête si déjà en panne
        return (self.soc_m <= self.soc_threshold_m
                and self.state == 'DRIVING'
                and self.soc_m > self.config.SOC_BREAKDOWN_THRESHOLD)

    def emit_request(self, current_time, loc_n, id_demand):
        charging_duration = self.generate_charging_duration_request(
            self.config.CHARGING_DURATION_PARAMS)
        x_n, y_n = loc_n
        max_waiting_time = np.random.randint(6, 24)
        max_dist = self.soc_m
        min_ray = min(self.config.MIN_RAY_SEARCH, self.config.COEFF_MAX_DIST * max_dist)
        max_ray = max(self.config.MIN_RAY_SEARCH, self.config.COEFF_MAX_DIST * max_dist)
        r_n = min(np.random.uniform(min_ray, max_ray), self.config.MAX_RAY_SEARCH)
        request = {
            'n':       id_demand,
            'car_idx': self.idx,
            't_n':     current_time,
            'd_n':     charging_duration,
            'loc':     (x_n, y_n),
            'r_n':     r_n,
            'g_n':     max_waiting_time
        }
        self.request = request
        return request

    def update_schedule_requested(self, min_dist):
        """FIX : == → = (affectation)"""
        t_arr = math.ceil(self.request['t_n'] + min_dist / self.config.CAR_SPEED)
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
        t_hat_arr = math.ceil(request['t_n'] + offer.distance / self.config.CAR_SPEED)

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

    def choose_offer(self, offers, request, min_dist):
        best_offer, best_u = None, -np.inf
        for offer in offers:
            u = self.compute_utility(offer, request, min_dist)
            if u > best_u:
                best_u = u
                best_offer = offer
        return best_offer, best_u

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
